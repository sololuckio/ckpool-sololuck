# SoloLuck's ckpool patches

SoloLuck runs [ckpool](https://bitbucket.org/ckolivas/ckpool) in solo mode. These are the
five patches it adds on top of upstream **v1.2.0** (`2e44101e`), published so the pool's
behaviour can be read rather than taken on trust.

ckpool is GPLv3. So are these. See [Licence](#licence) below.

SoloLuck has not found a Bitcoin block. Nothing in this repository changes that.

## Apply them yourself

```sh
git clone https://bitbucket.org/ckolivas/ckpool.git && cd ckpool
git checkout 2e44101e          # v1.2.0
git am /path/to/patches/*.patch
./autogen.sh && ./configure && make
```

Or run [`apply.sh`](apply.sh), which does exactly that and then prints the git tree hash of
the result so you can compare it against ours.

### Check you got what we got

All five apply to a clean v1.2.0 checkout in order, and the resulting tree is:

```
tree d58aef465a30d56cf6d1d883e4a8e5889180b5d9
```

```sh
git rev-parse HEAD^{tree}      # after git am
```

If that hash matches, your source tree is byte-for-byte the one these patches describe.
The commit hashes will differ from ours (`git am` stamps a fresh committer date); the tree
hash will not. The diff against upstream is seven source files, 576 insertions, 47 deletions:

```
 src/bitcoin.c    |  67 ++++++++--
 src/bitcoin.h    |   4 +
 src/ckpool.c     |  61 ++++++++-
 src/ckpool.h     |   2 +
 src/generator.c  | 368 +++++++++++++++++++++++++++++++++++++++++++++++++++----
 src/generator.h  |   1 +
 src/stratifier.c | 120 ++++++++++++++++--
 7 files changed, 576 insertions(+), 47 deletions(-)
```

That is the whole artifact. SoloLuck's two Bitcoin pools and its DigiByte pool run builds of
exactly this source. (Its Bitcoin Cash pool runs a different ckpool fork and does not use
these patches.)

## What each patch does

**0001 — per-port difficulty floors, lifetime reject counters, donation address**

The substantial one. It adds a `serverdiff` array to the config, giving each `serverurl`
its own minimum share difficulty, enforced in two places: when a client connects
(`serverdiff[server]` becomes that client's `suggest_diff`), and when a client sends
`mining.suggest_difficulty` (a lower value is raised to the floor). Neither path can go
below the floor for the port it arrived on.

This is what makes SoloLuck's tiers real rather than advisory:

| port | floor | for |
|---|---|---|
| 3335 | 1 | CPUs, NerdMiner-class devices |
| 3333 | 1,024 | Bitaxe, NerdQAxe, home ASICs |
| 3334 | 1,024 | same tier, TLS |
| 4334 | 1,048,576 | large or clustered ASICs, rented hashrate |

It also adds diff-weighted lifetime reject counters per user and per worker (published in
the stats JSON, and on each miner's page), and logs the server a client authorised on.

**Check the floors yourself.** A bare subscribe will not show them: every port starts a
connection at the pool's start difficulty (4,000) unless the port's floor is higher, and
asking straight for difficulty 1 on a port whose floor is 1,024 changes nothing, so the
pool sends nothing back. [`floorcheck.py`](floorcheck.py) (Python 3, standard library only)
subscribes, authorises with your address, asks for 2,048, then asks for 1, and prints the
difficulty the pool sets:

```sh
python3 floorcheck.py stratum.sololuck.io 3335 <your-bitcoin-address>          # floor 1
python3 floorcheck.py stratum.sololuck.io 3333 <your-bitcoin-address>          # floor 1,024
python3 floorcheck.py stratum.sololuck.io 3334 <your-bitcoin-address> --tls    # floor 1,024
python3 floorcheck.py stratum.sololuck.io 4334 <your-bitcoin-address>          # held at 1,048,576
```

It connects as a miner would, under `<your-address>.floorcheck`, so a worker with that name
appears on your own stats page. It submits no shares and disconnects after about fifteen
seconds.

**0002 — trim whitespace from the username before validating it**

A pasted address with a leading space was accepted and then mined to a second,
near-identical account. Worse: `bitcoind`'s `validateaddress` trims the space and calls the
address valid, while ckpool's own base58 decoder does not — so the coinbase would have been
built from the untrimmed string and paid a block to a script that is not the miner's
address. Silently wrong rather than rejected. This trims first, so the two validators agree
and the same address is always the same account.

**0003 — submit solved blocks to every configured bitcoind, save the block hex, lowercase bech32 usernames**

A solved block is submitted to every node, not just the one that built the template, and
the raw hex is written to disk. bech32 addresses are case-insensitive, so `BC1Q…` and
`bc1q…` logins are folded into one account instead of two.

**0004 — a dedicated submit connection per node**

Block submission gets its own thread and its own private socket per bitcoind rather than
sharing the general `getblocktemplate` connection, so a busy or stalled RPC socket cannot
delay it. Bounded: 8 s × 3 attempts per node, caller capped at 44 s, returns on the first
acceptance.

**0005 — a block nobody answered about is unresolved, not rejected**

Upstream ckpool never gave up on a solved block: it waited until a node came back. The
bounded fan-out in 0004 removed that wait, so with every bitcoind silent for 44 s a real
block was recorded as rejected and dropped. 0005 tells the difference between a verdict
(`null`, `duplicate`, or a named reason such as `bad-txnmrklroot`) and silence. Silence
now marks the block unresolved and hands it to a background thread that keeps resubmitting
on a backoff for up to 30 minutes, then prints the exact `bitcoin-cli` line to replay the
saved hex. A genuine rejection is still a rejection.

## About the 0% fee — read this rather than believe it

**The 0% is not in these patches.** It is a config value, and upstream ckpool's example
config is not zero.

ckpool takes a donation as a *percentage*, read from the config in
[`ckpool.c`](https://bitbucket.org/ckolivas/ckpool/src/master/src/ckpool.c) as `donation`,
set to 0 below 0.1. The coinbase donation output is only ever constructed inside this
branch in `stratifier.c`:

```c
if (ckpool.donvalid && ckpool.donation > 0) {
```

With `donation` at 0 that branch never runs, so no second output is built. SoloLuck's pools
run with `"donation": 0.0` (or with the key absent, which is also 0).

⚠️ **The `ckpool.conf` in the upstream source tree says `"donation" : 2.0`.** That is
upstream's shipped example, not ours.

Patch 0001 also repoints `donaddress` from upstream's address to SoloLuck's. That is the
address a donation *would* pay if one were ever configured. In solo mode with no
`btcaddress` set, ckpool also uses it to check that it can build a coinbase; it is never
mined to, and at `donation: 0.0` nothing is paid to it. It is the same address published at
[sololuck.io/costs](https://sololuck.io/costs?ref=ckpatch) — **do not put it in a miner**; your
miner's username must be your own address.

## What that argument does and does not prove

Publishing source does **not** prove the binary we run was built from it. Nobody should
accept that it does. What is published here is the source; what runs on the pool is a
binary we built, and you have only our word that they correspond. (Our builds use
different CPU flags per machine, so their hashes will not match a build of yours either.)

What the chain can show is what this software does with a block. SoloLuck **has not found
a Bitcoin block.** Its DigiByte pool, running a build of the first four patches, has solved
six DigiByte blocks:

| height | transactions in block | spendable coinbase outputs | fee output | reward |
|---|---|---|---|---|
| 24176239 | 1 | **1** | none | 253.55810338 DGB |
| 24175441 | 1 | **1** | none | 253.55810338 DGB |
| 24175188 | 1 | **1** | none | 253.55810338 DGB |
| 24163882 | 1 | **1** | none | 253.55810338 DGB |
| 24162973 | 1 | **1** | none | 253.55810338 DGB |
| 24162854 | 1 | **1** | none | 253.55810338 DGB |

**All six were found by machines the pool operator runs.** They show what the software
does with a reward — one spendable output holding the whole block reward, and no fee
output — not that an outside miner has been paid.

Each block carried no transaction other than its coinbase, so there were no transaction
fees and the reward is the block subsidy alone. You will count *two* coinbase outputs, not
one: the second is a zero-value `OP_RETURN` whose script begins `6a24aa21a9ed`, the BIP141
segwit commitment every segwit block carries. It moves no value and cannot be spent. And
each coinbase input's scriptSig ends in `ckpool` and `/sololuck.io/`, the pool's signature.

Check any of them yourself, on two explorers we do not run:

```sh
H=$(curl -s "https://chainz.cryptoid.info/dgb/api.dws?q=getblockhash&height=24176239" | tr -d '"')

curl -s "https://digiexplorer.info/api/block/$H" \
  | python3 -c 'import json,sys; b=json.load(sys.stdin); print("height", b["height"], "transactions", b["tx_count"])'

curl -s "https://digiexplorer.info/api/block/$H/txs" | python3 -c '
import json, sys
cb = json.load(sys.stdin)[0]
for o in cb["vout"]:
    print(o["scriptpubkey_type"], o["value"])
print("scriptSig text:", "".join(chr(c) if 32 <= c < 127 else " " for c in bytes.fromhex(cb["vin"][0]["scriptsig"])).split()[-2:])'
```

Expected: `transactions 1`; one `v0_p2wpkh` output of `25355810338` and one `op_return` of
`0`; `scriptSig text: ['ckpool', '/sololuck.io/']`.

DigiByte is a different chain with difficulty orders of magnitude below Bitcoin's, and
these blocks say nothing about anyone's odds of finding a Bitcoin block.

## What is not here

The website that serves sololuck.io is a separate codebase and is **not** in this
repository. SoloLuck's open-source miner, and a front-end reference for the stats page,
are published separately under the MIT licence at
[github.com/sololuckio/sololuck](https://github.com/sololuckio/sololuck).

## Licence

**GPL-3.0-or-later.** ckpool is copyright © 2014–2026 Con Kolivas and is distributed under
the GNU General Public License version 3 or later. These patches are modifications of it
and carry the same licence. The full text is in [COPYING](COPYING); attribution and
provenance are in [NOTICE](NOTICE).

Nothing in this repository is offered under any other licence.

---

[sololuck.io](https://sololuck.io/?ref=ckpatch) · the pool's own stats are at `/api/public`, unauthenticated and
documented at `/api`.
