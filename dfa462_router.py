_DR_UNSET = object()
import json as _dl_json, os as _dl_os
from minotaur_subnet.shared.types import ExecutionPlan as _DLPlan, Interaction as _DLIx

def _dl_consts():
    weth = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
    usdc = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
    maj = {t.lower() for t in (weth, usdc, '0x6B175474E89094C44Da98b954EedeAC495271d0F', '0xdAC17F958D2ee523a2206206994597C13D831ec7', '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')}
    return ('0x61fFE014bA17989E743c5F6cB21bF9697530B21e', '0xE592427A0AEce92De3Edee1F18E0157C05861564', weth, usdc, maj, (100, 500, 3000, 10000), '04e45aaf', '414bf389', 'b858183f', 'c04b8d59', ('ac9650d8', '5ae401dc'))
_ETH_QUOTER, _ETH_ROUTER, _ETH_WETH, _ETH_USDC, _ETH_MAJ, _DL_FEES, _SEL_EIS_02, _SEL_EIS, _SEL_EI_02, _SEL_EI, _SEL_MC = _dl_consts()

def _dl_sel(sig):
    from eth_utils import keccak
    return '0x' + keccak(sig.encode())[:4].hex()

def _dl_ethcall(handle, to, data):
    try:
        if isinstance(handle, str):
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(handle, request_kwargs={'timeout': 9}))
        elif handle is not None and getattr(handle, 'provider', None) is not None:
            w3 = handle
        else:
            return None
        res = w3.provider.make_request('eth_call', [{'to': to, 'data': data}, 'latest']).get('result')
        return res if res and res != '0x' else None
    except Exception:
        return None

def _dl_qsingle(url, tin, tout, amt, fee):
    from eth_abi import encode
    data = _dl_sel('quoteExactInputSingle((address,address,uint256,uint24,uint160))') + encode(['(address,address,uint256,uint24,uint160)'], [(tin, tout, int(amt), fee, 0)]).hex()
    r = _dl_ethcall(url, _ETH_QUOTER, data)
    return int(r[2:66], 16) if r and len(r) >= 66 else 0

def _dl_qpath(url, tokens, fees, amt):

    def _dz42():
        data = _dl_sel('quoteExactInput(bytes,uint256)') + encode(['bytes', 'uint256'], [b, int(amt)]).hex()
        r = _dl_ethcall(url, _ETH_QUOTER, data)
        return (int(r[2:66], 16) if r and len(r) >= 66 else 0,)
        return _DR_UNSET
    from eth_abi import encode
    b = b''
    for i, t in enumerate(tokens):
        b += bytes.fromhex(t[2:])
        if i < len(fees):
            b += int(fees[i]).to_bytes(3, 'big')
    _r_dz42 = _dz42()
    if _r_dz42 is not _DR_UNSET:
        return _r_dz42[0]
_BAL_VAULT = '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
_BAL_TBL = '8399c8fc273bd165c346af74a02e65f10e4fd78fe2fc85bfb48c4cf147921fbe110cf92ef9f26f94ae255db04ba78519f33871c557d8fd6bafdb83bd;7f39c581f595b53c5cb19bd0b3f8da6c935e2ca07fc66500c84a76ad7e9c93437bfc5ac33e2ddae93de27efa2f1aa663ae5d458857e731c129069f29000200000000000000000588;0bfc9d54fc184518a81162f8fb99c2eaca081202ae78736cd615f374d3085123a210448e74fc63931ea5870f7c037930ce1d5d8d9317c670e89e13e3;ba100000625a3754423978a60c9317c58a424e3dc02aaa39b223fe8d0a0e5c4f27ead9083c756cc25c6ee304399dbdb9c8ef030ab642b10820db8f56000200000000000000000014;2260fac5e5542a773aa44fbcfedf7c193bc2c599c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2a6f548df93de924d73be7d25dc02554c6bd66db500020000000000000000000e;0bfc9d54fc184518a81162f8fb99c2eaca081202f1c9acdc66974dfb6decb12aa385b9cd01190e3857c23c58b1d8c3292c15becf07c62c5c52457a42;775f661b0bd1739349b9a2a3ef60be277c5d2d29d11c452fc99cf405034ee446803b6f6c1f6d5ed89ed5175aecb6653c1bdaa19793c16fd74fbeeb37;559b7bfc48a5274754b08819f75c5f27af53d53bc02aaa39b223fe8d0a0e5c4f27ead9083c756cc239eb558131e5ebeb9f76a6cbf6898f6e6dce5e4e0002000000000000000005c8;ae8535c23afedda9304b03c68a3563b75fc8f92bbb6881874825e60e1160416d6c426eae65f2459eae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;ae8535c23afedda9304b03c68a3563b75fc8f92bf951e335afb289353dc249e82926178eac7ded78ae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;bb6881874825e60e1160416d6c426eae65f2459ef951e335afb289353dc249e82926178eac7ded78ae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;6810e776880c02933d47db1b9fc05908e5386b96def1ca1fb7fbcdc777520aa7f396b4e015f497ab92762b42a06dcdddc5b7362cfb01e631c4d44b40000200000000000000000182;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2fd0205066521550d7d7ab19da8f72bb004b4c3419232a548dd9e81bac65500b5e0d918f8ba93675c000200000000000000000423;0fe906e030a44ef24ca8c7dc7b7c53a6c4f00ce977146784315ba81904d654466968e3a7c196d1f3daba3d8ccf79ef289a7e2dbce51871b39ea445a2;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2dbdb4d16eda451d0503b854cf79d55697f90c8df1535d7ca00323aa32bd62aeddf7ca651e4b95966;4cbde5c4b4b53ebe4af4adb85404725985406163a35b1b31ce002fbf2058d22f30f95d405200a15b4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;4cbde5c4b4b53ebe4af4adb85404725985406163bb6881874825e60e1160416d6c426eae65f2459e4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;a35b1b31ce002fbf2058d22f30f95d405200a15bbb6881874825e60e1160416d6c426eae65f2459e4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;79c71d3436f39ce382d0f58f1b011d88100b9d91c02aaa39b223fe8d0a0e5c4f27ead9083c756cc21bccaac02bae336c6352acc3b772059ef1142fa70002000000000000000001f0;68917a0e538cf4a807b3d415c1af5cdbab0ff4dca0b86991c6218b36c1d19d4a2e9eb0ce3606eb4848995dbdca50fa5346b0771d40a5ae7664262f7e;7bc3485026ac48b6cf9baf0a377477fff5703af8c71ea051a5f82c67adcf634c36ffe6334793d24c85b2b559bc2d21104c4defdd6efca8a20343361d;7bc3485026ac48b6cf9baf0a377477fff5703af8d4fa2d31b7968e448877f69a96de69f5de8cd23e85b2b559bc2d21104c4defdd6efca8a20343361d;c71ea051a5f82c67adcf634c36ffe6334793d24cd4fa2d31b7968e448877f69a96de69f5de8cd23e85b2b559bc2d21104c4defdd6efca8a20343361d;a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48c02aaa39b223fe8d0a0e5c4f27ead9083c756cc296646936b91d6b9d7d0c47c496afbf3d6ec7b6f8000200000000000000000019;2260fac5e5542a773aa44fbcfedf7c193bc2c599eb4c2781e4eba804ce9a9803c67d0893436bb27dfeadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;2260fac5e5542a773aa44fbcfedf7c193bc2c599fe18be6b3bd88a2d2a7f928d00292e7a9963cfc6feadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;eb4c2781e4eba804ce9a9803c67d0893436bb27dfe18be6b3bd88a2d2a7f928d00292e7a9963cfc6feadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2cfeaead4947f0705a14ec42ac3d44129e1ef3ed55122e01d819e58bb2e22528c0d68d310f0aa6fd7000200000000000000000163;9f8f72aa9304c8b593d555f12ef6589cc3a579a2c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2aac98ee71d4f8a156b6abaa6844cdb7789d086ce00020000000000000000001b;1cf0f3aabe4d12106b27ab44df5473974279c524c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2ea39581977325c0833694d51656316ef8a926a62000200000000000000000036;6b175474e89094c44da98b954eedeac495271d0fc02aaa39b223fe8d0a0e5c4f27ead9083c756cc20b09dea16768f0799065c475be02919503cb2a3500020000000000000000001a;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f8353157092ed8be69a9df8f95af097bbf33cb2af8353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2fa0b86991c6218b36c1d19d4a2e9eb0ce3606eb488353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2fdac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;8353157092ed8be69a9df8f95af097bbf33cb2afa0b86991c6218b36c1d19d4a2e9eb0ce3606eb488353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;8353157092ed8be69a9df8f95af097bbf33cb2afdac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48dac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;3839a0dd920463eb5d8231efe4d8c5edc44145ecd4fa2d31b7968e448877f69a96de69f5de8cd23e51cdf9cc199f8121b58d9337983a79a1b87330fd;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2ec53bf9167f50cdeb3ae105f56099aaab9061f83bda917a67c7d9ae67da92c4ea87e10e5d6c11b54;4ba01f22827018b4772cd326c7627fb4956a7c00890a5122aa1da30fec4286de7904ff808f0bd74a9054ae85300c7d3a325714fc2f1454d0b7c73a12;3c640f0d3036ad85afa2d5a9e32be651657b874f50cf90b954958480b8df7958a9e965752f62712450cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;3c640f0d3036ad85afa2d5a9e32be651657b874fd4e7c1f3da1144c9e2cfd1b015eda7652b4a439950cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;3c640f0d3036ad85afa2d5a9e32be651657b874feb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;50cf90b954958480b8df7958a9e965752f627124d4e7c1f3da1144c9e2cfd1b015eda7652b4a439950cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;50cf90b954958480b8df7958a9e965752f627124eb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;d4e7c1f3da1144c9e2cfd1b015eda7652b4a4399eb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;35e78b3982e87ecfd5b3f3265b601c046cdbe232a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48f506984c16737b1a9577cadeda02a49fd612aff80002000000000000000002a9;6c0aeceedc55c9d55d8b99216a670d85330941c3c02aaa39b223fe8d0a0e5c4f27ead9083c756cc21846c6cbe0d433e152fa358e5ff27968e18bce7c;44108f0223a3c3028f5fe7aec7f9bb2e66bef82f7f39c581f595b53c5cb19bd0b3f8da6c935e2ca036be1e97ea98ab43b4debf92742517266f5731a3000200000000000000000466;c0c17dd08263c16f6b64e772fb9b723bf1344ddfe108fbc04852b5df72f9e44d7c29f47e7a993adde00e947decfe01692070e113002705bdf77ddbd3;a3931d71877c0e7a3148cb7eb4463524fec27fbdf3b5b661b92b75c71fa5aba8fd95d7514a9cd605642bb6860b4776cc10b26b8f361fd139e7f0db04;97ccc1c046d067ab945d3cf3cc6920d3b1e54c88d4fa2d31b7968e448877f69a96de69f5de8cd23e114907c2a07978c38ebb9f9f6a5261a846b79521'
_BAL_MAP = {}

def _dl_bal_ix(tin, tout, amt, recipient, pid):
    """approve + Vault.swap interactions for a single-pool Balancer swap."""

    def _dz41():
        sig = 'swap((bytes32,uint8,address,address,uint256,bytes),(address,bool,address,bool),uint256,uint256)'
        swap = _dl_sel(sig) + encode(['(bytes32,uint8,address,address,uint256,bytes)', '(address,bool,address,bool)', 'uint256', 'uint256'], [(bytes.fromhex(pid[2:]), 0, tin, tout, amt, b''), (recipient, False, recipient, False), 1, 9999999999]).hex()
        return ([_DLIx(target=tin, value='0', call_data=approve, chain_id=1), _DLIx(target=_BAL_VAULT, value='0', call_data=swap, chain_id=1)],)
        return _DR_UNSET
    from eth_abi import encode
    amt = int(amt)
    approve = '0x095ea7b3' + _BAL_VAULT[2:].rjust(64, '0').lower() + amt.to_bytes(32, 'big').hex()
    _r_dz41 = _dz41()
    if _r_dz41 is not _DR_UNSET:
        return _r_dz41[0]

def _dl_eth_ix(tin, tout, amt, recipient, route, min_out=1):

    def _dz39():
        if kind == 'bal':
            return (_dl_bal_ix(tin, tout, amt, recipient, route[1][1]),)
        return _DR_UNSET

    def _dz38(route):
        tokens, fees = (route[1][1], route[1][2])
        _dz34()
        return (fees, tokens)

    def _dz37():
        return ([_DLIx(target=tin, value='0', call_data=approve, chain_id=1), _DLIx(target=_ETH_ROUTER, value='0', call_data=swap, chain_id=1)],)
        return _DR_UNSET

    def _dz36(amt, mo, recipient, route, tin, tout):
        fee = route[1][1]
        swap = _dl_sel('exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))') + encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(tin, tout, int(fee), recipient, 9999999999, amt, mo, 0)]).hex()
        return (fee, swap)

    def _dz35(amt, min_out, route):
        amt = int(amt)
        mo = int(min_out)
        approve = '0x095ea7b3' + _ETH_ROUTER[2:].rjust(64, '0').lower() + amt.to_bytes(32, 'big').hex()
        kind = route[1][0]
        return (amt, approve, kind, mo)

    def _dz34():
        nonlocal swap
        b = b''
        for i, t in enumerate(tokens):
            b += bytes.fromhex(t[2:])
            if i < len(fees):
                b += int(fees[i]).to_bytes(3, 'big')
        swap = _dl_sel('exactInput((bytes,address,uint256,uint256,uint256))') + encode(['(bytes,address,uint256,uint256,uint256)'], [(b, recipient, 9999999999, amt, mo)]).hex()
    from eth_abi import encode
    amt, approve, kind, mo = _dz35(amt, min_out, route)
    _r_dz39 = _dz39()
    if _r_dz39 is not _DR_UNSET:
        return _r_dz39[0]
    if kind == 'single':
        fee, swap = _dz36(amt, mo, recipient, route, tin, tout)
    else:
        fees, tokens = _dz38(route)
    _r_dz37 = _dz37()
    if _r_dz37 is not _DR_UNSET:
        return _r_dz37[0]
_DL_UNI_FACTORY = '0x1F98431c8aD98523631AE4a59f267346ea31F984'

def _dl_getpool(url, a, b, fee):
    """UniV3 pool address for (a,b,fee) or None. A view call — does NOT revert on
    fee-on-transfer / quoter-hostile tokens, unlike QuoterV2. Zero addr => no pool."""
    from eth_abi import encode
    data = _dl_sel('getPool(address,address,uint24)') + encode(['address', 'address', 'uint24'], [a, b, int(fee)]).hex()
    r = _dl_ethcall(url, _DL_UNI_FACTORY, data)
    if not (r and len(r) >= 66):
        return None
    addr = '0x' + r[-40:]
    return addr if int(addr, 16) != 0 else None

def _dl_poolliq(url, pool):
    """UniV3 pool in-range liquidity (0 = empty/uninitialized). View call, FoT-safe."""
    r = _dl_ethcall(url, pool, _dl_sel('liquidity()'))
    try:
        return int(r, 16) if r and r != '0x' else 0
    except Exception:
        return 0

def _dl_blind_route(url, tin, tout):
    """Find a UniV3 route by POOL EXISTENCE + LIQUIDITY (no quote) — for blinds whose output
    token breaks QuoterV2 (fee-on-transfer). Requires liquidity>0 so we skip existing-but-EMPTY
    pools (e.g. RLB/USDT is empty; RLB/WETH is not -> pick the 2-hop). Direct first, else 2-hop
    via WETH. Returns a ("single",fee)/("path",...) route or None; caller uses min_out=0."""

    def _dz33():
        for f2 in (10000, 3000, 500, 100):
            p2 = _dl_getpool(url, w, tout, f2)
            if not (p2 and _dl_poolliq(url, p2) > 0):
                continue
            for f1 in (500, 3000, 100):
                p1 = _dl_getpool(url, tin, w, f1)
                if p1 and _dl_poolliq(url, p1) > 0:
                    return (('path', [tin, w, tout], [f1, f2]),)
        return _DR_UNSET
    for f in (10000, 3000, 500, 100):
        p = _dl_getpool(url, tin, tout, f)
        if p and _dl_poolliq(url, p) > 0:
            return ('single', f)
    w = _ETH_WETH
    if w.lower() not in (tin.lower(), tout.lower()):
        _r_dz33 = _dz33()
        if _r_dz33 is not _DR_UNSET:
            return _r_dz33[0]
    return None

def _dl_v2c():
    return ('0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e', 'c872a3c5', '81889a2c', ('5c11d795', '38ed1739'), 'd06ca61f', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D')
_DL_CURVE_RTR, _SEL_CURVE_EX, _SEL_CURVE_DY, _SEL_UNIV2, _SEL_GAO, _DL_UNIV2_RTR = _dl_v2c()

def _dz42():
    _XC_CANON = {'weth': {1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 8453: '0x4200000000000000000000000000000000000006'}, 'usdc': {1: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 8453: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'}}
    _XC_ROUTER = {1: '0xE592427A0AEce92De3Edee1F18E0157C05861564', 8453: '0x2626664c2603336E57B271c5C0b26F421741e481'}
    _XC_ANVIL = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'
    return (_XC_CANON, _XC_ROUTER, _XC_ANVIL)
_XC_CANON, _XC_ROUTER, _XC_ANVIL = _dz42()