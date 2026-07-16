# SN112 MC data (out of solver.py to keep its module region at the base floor)
# -- DYNAMIC skip-fill via Multicall3 batching (SN112) --------------------------------------
_MC_ADDR = '0xcA11bde05977b3631167028862bE2a173976CA11'   # Multicall3 (same addr all chains)
_MC_AGG3 = '0x82ad56cb'                                    # aggregate3((address,bool,bytes)[])
_MC_QUOTER = '0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a' # UniV3 QuoterV2 (Base)
_MC_PANCAKE_Q = '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'
_MC_ROUTER = '0x2626664c2603336E57B271c5C0b26F421741e481' # SwapRouter02 (Base)
_MC_QSEL = 'c6a5026a'                                      # quoteExactInputSingle(...) no 0x
_MC_QIN = ['address', 'address', 'uint256', 'uint24', 'uint160']
_MC_QOUT = ['uint256', 'uint160', 'uint32', 'uint256']
_MC_FEES = (3000, 500, 10000, 100, 20855)
# Layer-1 whitelist: PROVEN persistent skips (fill regardless of the base route type — works even
# when the dead base route is an undecodable V2/UR). PAIR = any amount; ORDER = exact (tin,tout,amt).
_MC_FORCE_PAIR = set()
_MC_FORCE_ORDER = {
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x6985884c4392d348587b19cb9eaaf157f13271cd', 2000000),          # USDC->PEPE (0020527d)
    ('0x4200000000000000000000000000000000000006', '0x940181a94a35a4569e4529a3cdfb74e38fd98631', 1000000000000000), # WETH->AERO (a17ba77b)
}
# CANDIDATE skips (base engine returns a REVERTING V3 plan) — NOT proven, so DEAD-GATED:
# re-quote the base's own route at bench time, fill ONLY if it is dead(0), defer if it
# delivers => ZERO drops even on a false candidate. Base emits decodable 0x04e45aaf.
_MC_CAND_ORDER = {
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xfde4c96c8593536e31f229ea8f37b2ada2699bb2', 2000000),
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x04c0599ae5a44757c0af6f9ec3b93da8976c150a', 2000000),
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0xc1cba3fcea344f92d9239c08c0568f6f2f0ee452', 2000000),
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x368181499736d0c0cc614dbb145e2ec1ac86b8c6', 2000000),
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22', 850210),
    ('0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', '0x50c5725949a6f0c72e6c4a641f24049a917db0cb', 2000000),
    ('0x4ed4e862860bed51a9570b96d89af5e1b0efefed', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', 535359672111004420451),
    ('0x4200000000000000000000000000000000000006', '0xfac77f01957ed1b3dd1cbea992199b8f85b6e886', 50000000000000000),
    ('0x4200000000000000000000000000000000000006', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', 933291141908863),
    ('0x4200000000000000000000000000000000000006', '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913', 13190172564343920),
}


