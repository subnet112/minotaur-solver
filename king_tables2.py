"""Engine route tables (split out of king_base.py for the factorization
metric — pure data, no logic)."""
from king_consts import *  # noqa: F401,F403

_HOLE_ROUTES = {
    # token: ("maverick", (pool_address, tokenAIn_for_USDC->token))
    "0xad20523a7dc37babc1cc74897e4977232b3d02e5":
        ("maverick", ("0x73be69ad437d636b12cc4804701b5283cb4285f5", True)),
    "0x0963a1abaf36ca88c21032b82e479353126a1c4b":
        ("maverick", ("0x5d5b4bfa3619ee3b49a154cfdf7243359570aafe", False)),
    # Direct USDC->token single-hop on the token's deep tier, built RPC-free.
    "0x6921c09f2b5cee21a929591a070d4b0354dbee8d":
        ("sushi_v3", 100),
    # SNSY: verified UNSUPPORTED hole — live corpus order WETH->SNSY scores 0.0
    # (champion cannot fill), v41 fills via Sushi (fork /score success, 1.0).
    # WETH-paired pool; a non-WETH input reverts -> 0 == champion's 0 -> skip.
    # (BEPE was tested too but scores 1.0 — champion DOES route it via live
    # enumeration despite offline-empty quote; NOT sealed, would regress.)
    "0x3124678d62d2aa1f615b54525310fbfda6dcf7ae":  # SNSY  (Sushi V3 WETH/SNSY fee 10000)
        ("sushi_v3", 10000),
    # king v46: Hydrex (Algebra Integral) — a venue this base cannot reach, so
    # these score 0/None (blind_spot_cover vs champion). Single-hop
    # exactInputSingle tin->tout; param = VERIFIED-good input tokens (a direct
    # Hydrex pool exists for that pair) so other inputs fall through to baseline
    # instead of emitting a guaranteed-revert plan. HYDX: HYDX/USDC (~$298k) +
    # HYDX/WETH -> wins USDC->HYDX (8712 HYDX) AND WETH->HYDX. DEXTF: WETH/DEXTF
    # (~$64k) -> wins WETH->DEXTF. Fork-verified via /score at 1.0.
    "0x00000e7efa313f4e11bfff432471ed9423ac6b30":  # HYDX (Hydrex Algebra)
        ("hydrex", (_USDC, _WETH)),
    "0xb69bbb15095c0949489fbb43951d2b750fa7fa89":  # DEXTF (Hydrex Algebra)
        ("hydrex", (_WETH,)),
    # king v47: 6 more Hydrex (Algebra Integral) holes — all champion (top-miner
    # v0.84) /quote=0, all with a direct USDC- or WETH-paired Hydrex pool so the
    # single-hop exactInputSingle fills. param = verified-good input token.
    "0x55380fe7a1910dff29a47b622057ab4139da42c5":  # FXUSD (Hydrex USDC ~$337k)
        ("hydrex", (_USDC,)),
    "0xc48823ec67720a04a9dfd8c7d109b2c3d6622094":  # MCADE (Hydrex WETH ~$125k)
        ("hydrex", (_WETH,)),
    "0x3e31966d4f81c72d2a55310a6365a56a4393e98d":  # WMTX (Hydrex WETH ~$77k)
        ("hydrex", (_WETH,)),
    "0xb99b6df96d4d5448cc0a5b3e0ef7896df9507cf5":  # VAULT (Hydrex USDC ~$47k)
        ("hydrex", (_USDC,)),
    "0x5cda0e1ca4ce2af96315f7f8963c85399c172204":  # wtCOIN (Hydrex USDC ~$21k)
        ("hydrex", (_USDC,)),
    # king v47 (2nd batch): 4 more Hydrex holes (champion /quote=0, direct pool).
    "0x16edb4dfc1d3368d051370699edfb280e9a1b474":  # 40ACRES (Hydrex USDC ~$22k)
        ("hydrex", (_USDC,)),
    "0x7afe438411ee3959c7de6f7fb76bf9c769320ba3":  # BLOCKTRONICS (Hydrex USDC ~$13k)
        ("hydrex", (_USDC,)),
    # king v64: FACY hydrex pool now REVERTS (scored 0.0); the live venue is the
    # direct Aerodrome V2 USDC pool (audit: 1279e18 vs hydrex 0).
    "0xfac77f01957ed1b3dd1cbea992199b8f85b6e886":  # FACY (Aero V2 USDC direct)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x6e0090dbecf3b4f0f9429637756cadd8fc468c54":  # MILK (Hydrex WETH ~$9k)
        ("hydrex", (_WETH,)),
    # king 1.2.0: Aerodrome V2 pairs on the CANONICAL Aerodrome factory
    # (0x420DD381...e40da — the same factory the base already has an
    # aerodrome_v2 encoder for) that just aren't in the base's hardcoded
    # allowlist. On-chain-confirmed non-drained volatile WETH pools.
    "0xfb31f85a8367210b2e4ed2360d2da9dc2d2ccc95":  # EDEL (Aero V2 WETH ~$597k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0x8c0d3adcf8ce094e1ae437557ec90a6374dc9bdd":  # OVPP (Aero V2 WETH ~$391k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    # king v85: discovery-win token from e29718073 A/B (we serve via aero-CL
    # discovery, champ drops). Aero V2 volatile WETH pool on the CANONICAL
    # factory (0xc238f8ea; factory+stable=False on-chain confirmed) — static-seal
    # so it serves at the instant intercept (survives v84 behind-pace gating)
    # instead of depending on live discovery. WETH-in single hop.
    "0x01facc69ec7360640aa5898e852326752801674a":  # (Aero V2 WETH)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    # king v50: 20 more Aerodrome V2 (canonical factory) holes from the
    # 2026-07-02 sweep — every one /quote=0 both dirs vs champion AND
    # on-chain getReserves() nonzero AND /score-validated 1.0 before ship.
    # All volatile pools direct-paired with the verified input token.
    "0xeab49138ba2ea6dd776220fe26b7b8e446638956":  # SEND (USDC ~$1.42M)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x93dc5cb35627a759848c7a7f0079ea7b49e435a5":  # MET (WETH ~$1.26M)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0x9b5e262cf9bb04869ab40b19af91d2dc85761722":  # NOCK (USDC ~$935k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x767a739d1a152639e9ea1d8c1bd55fdc5b217d7f":  # VEIL (WETH ~$460k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0x1b4617734c43f6159f3a70b7e06d883647512778":  # AWE (USDC ~$359k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0xed9ae3def8d6f052971bb8b6d1975ff267cf9aad":  # BLUAI (WETH ~$170k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0xe88419a3fc78364cfe3de88080ee4853fab754c6":  # ROBA (USDC ~$128k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x0dc28efba8c6e0c14fa7391636b8bec86c4c83d6":  # BSB (USDC ~$110k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x3bbcb624cb9a1f73163a886f460f47603e5e4425":  # HANDL (USDC ~$91k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0xe2b1dc2d4a3b4e59fdf0c47b71a7a86391a8b35a":  # RWA (USDC ~$88k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0xef5997c2cf2f6c138196f8a6203afc335206b3c1":  # OWB (USDC ~$79k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0x11dc28d01984079b7efe7763b533e6ed9e3722b9":  # SYND (WETH ~$79k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0x7431ada8a591c955a994a21710752ef9b882b8e3":  # MOR (WETH ~$63k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0xc0041ef357b183448b235a8ea73ce4e4ec8c265f":  # COOKIE (WETH ~$55k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0xeffc8815487084a97edfdff968b56ea123421acb":  # VIBES (WETH ~$47k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0xa81a52b4dda010896cdd386c7fbdc5cdc835ba23":  # TRAC (WETH ~$39k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    # DAG/OFC/Kendu/ZERC: initial /score reverts were CustomError 0x203d82d8
    # = Aerodrome Expired() (drifted-anvil deadline artifact, NOT a factory
    # mismatch — on-chain factory()==canonical, stable()==false for all 4).
    # Re-sealed after the constant-deadline hardening.
    "0xecff4d80f54cf55c626e52f304a8891645961e72":  # DAG (WETH ~$32k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0x752c5a95d202972e124390f30a50154409d3c858":  # OFC (USDC ~$32k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    "0xef73611f98da6e57e0776317957af61b59e09ed7":  # Kendu (WETH ~$28k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH)),
    "0xa3a2cdd230f9b3ff6e01a01534a3ed3cbf049815":  # ZERC (USDC ~$25k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC)),
    # king v51: QuickSwap V4 (Algebra) WETH-paired pools, liquidity()>0 verified.
    # king v66: SYMM REVERTED to quickswap. The v64 aero upgrade won USDC->SYMM
    # at $2 (256e18 vs 136e18) but LOST WETH->SYMM at 0.05 WETH (10905e18 vs
    # champ quickswap 11091e18 = -1.67% regression, e29716962). The Algebra
    # WETH/SYMM pool ($392k) is deeper; quickswap matched ALL directions for
    # weeks. Safety over one win row.
    "0x800822d361335b4d5f352dac293ca4128b5b605f":  # SYMM (QuickSwap WETH ~$392k)
        ("quickswap", (_WETH,)),
    "0x7094c27f342dbadfbbed005b219431595e33b305":  # QUICK (QuickSwap WETH ~$95k)
        ("quickswap", (_WETH,)),
    "0x9bba915f036158582c20b51113b925f243a1a1a1":  # IMGN (QuickSwap WETH ~$88k)
        ("quickswap", (_WETH,)),
    # king v52: 6 more QuickSwap V4 (Algebra) direct pools, liquidity()>0.
    "0x3597194c3b8a9481141fb9c628fc398c120a58a9":  # RYFT (WETH ~$47k)
        ("quickswap", (_WETH,)),
    "0xae35ff1bc4fbb45aaeef9768a3d9610786cac98b":  # stratETH (WETH ~$42k)
        ("quickswap", (_WETH,)),
    "0x16332535e2c27da578bc2e82beb09ce9d3c8eb07":  # ClawBank (WETH ~$11.7k)
        ("quickswap", (_WETH,)),
    "0xe5f2fe713cdb192c85e67a912ff8891b4e636614":  # stratUSD (USDC ~$39k)
        ("quickswap", (_USDC,)),
    "0x9886447ff4c350f4600e4bf95db756bdc629b1ca":  # CERE (USDC ~$35k)
        ("quickswap", (_USDC,)),
    "0x862a1226e6ea04e34ea3ddb4346c7a2c693e06ab":  # PENMT (USDC ~$19k)
        ("quickswap", (_USDC,)),
    # king v52: BaseSwap V2 (UniV2 fork) WETH-paired pools, reserves verified.
    # Generic V2-fork kind: param = (router, verified_input, optional hub).
    "0x546d239032b24eceee0cb05c92fc39090846adc7":  # SEED (BaseSwap WETH ~$41k)
        ("v2_router", ("0x327Df1E6de05895d2ab08513aaDD9313Fe505d86", _WETH)),
    "0x78a087d713be963bf307b18f2ff8122ef9a63ae9":  # BSWAP (BaseSwap WETH ~$16k)
        ("v2_router", ("0x327Df1E6de05895d2ab08513aaDD9313Fe505d86", _WETH)),
    "0x90678c02823b21772fa7e91b27ee70490257567b":  # ALTITUDE (BaseSwap WETH ~$14k)
        ("v2_router", ("0x327Df1E6de05895d2ab08513aaDD9313Fe505d86", _WETH)),
    # king v52: Alien Base V3 (UniV3 fork, SwapRouter02-style NO-deadline
    # exactInputSingle 0x04e45aaf). MONSTRO pool fee=10000/tick200, liq>0.
    "0x1d3be1cc80ca89ddbabe5b5c254af63200e708f7":  # MONSTRO (USDC ~$17.9k)
        ("alien_v3", (10000, _USDC)),
    # king v52: Equalizer (Solidly fork, Route[] WITHOUT factory field,
    # swapExactTokensForTokens selector 0xf41766d8). Reserves verified.
    "0xe2a74f0847c8bd4a55418fea488831ad6a0cc998":  # PZERO (Equalizer USDC ~$11.7k)
        ("equalizer", (_USDC,)),
    "0xbef29bcffffc0c435f64eb4058c890c8f269415c":  # OPP (Equalizer USDC ~$14.3k)
        ("equalizer", (_USDC,)),
    # king v52: SOGNI — Aero V2 two-leg via USDT hub; leg1 USDC->USDT is the
    # STABLE pool (4-tuple param adds the leg1 stable flag).
    "0xe014d2a4da6e450f21b5050120d291e63c8940fd":  # SOGNI (via USDT, ~$233k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC,
                     "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", True)),
    # king v51: exotic-paired Aerodrome V2 tokens via two-leg Route[] through
    # a hub (both legs canonical-factory volatile, reserves verified on-chain).
    "0x74ccbe53f77b08632ce0cb91d3a545bf6b8e0979":  # fBOMB (via AERO, ~$1.7M)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _USDC,
                     "0x940181a94a35a4569e4529a3cdfb74e38fd98631")),
    "0x9eaf8c1e34f05a589eda6bafdf391cf6ad3cb239":  # YFI (via wstETH, ~$890k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH,
                     "0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452")),
    "0x940a319b75861014a220d9c6c144d108552b089b":  # DEUS (via VIRTUAL, ~$811k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH,
                     "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b")),
    "0xed6e000def95780fb89734c07ee2ce9f6dcaf110":  # EDGE (via cbBTC, ~$468k)
        ("aero_v2", ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", _WETH,
                     "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf")),
}
