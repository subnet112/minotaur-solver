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

    def _dz63():
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
    _r_dz63 = _dz63()
    if _r_dz63 is not _DR_UNSET:
        return _r_dz63[0]
_BAL_VAULT = '0xBA12222222228d8Ba445958a75a0704d566BF2C8'
_BAL_TBL = '8399c8fc273bd165c346af74a02e65f10e4fd78fe2fc85bfb48c4cf147921fbe110cf92ef9f26f94ae255db04ba78519f33871c557d8fd6bafdb83bd;7f39c581f595b53c5cb19bd0b3f8da6c935e2ca07fc66500c84a76ad7e9c93437bfc5ac33e2ddae93de27efa2f1aa663ae5d458857e731c129069f29000200000000000000000588;0bfc9d54fc184518a81162f8fb99c2eaca081202ae78736cd615f374d3085123a210448e74fc63931ea5870f7c037930ce1d5d8d9317c670e89e13e3;ba100000625a3754423978a60c9317c58a424e3dc02aaa39b223fe8d0a0e5c4f27ead9083c756cc25c6ee304399dbdb9c8ef030ab642b10820db8f56000200000000000000000014;2260fac5e5542a773aa44fbcfedf7c193bc2c599c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2a6f548df93de924d73be7d25dc02554c6bd66db500020000000000000000000e;0bfc9d54fc184518a81162f8fb99c2eaca081202f1c9acdc66974dfb6decb12aa385b9cd01190e3857c23c58b1d8c3292c15becf07c62c5c52457a42;775f661b0bd1739349b9a2a3ef60be277c5d2d29d11c452fc99cf405034ee446803b6f6c1f6d5ed89ed5175aecb6653c1bdaa19793c16fd74fbeeb37;559b7bfc48a5274754b08819f75c5f27af53d53bc02aaa39b223fe8d0a0e5c4f27ead9083c756cc239eb558131e5ebeb9f76a6cbf6898f6e6dce5e4e0002000000000000000005c8;ae8535c23afedda9304b03c68a3563b75fc8f92bbb6881874825e60e1160416d6c426eae65f2459eae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;ae8535c23afedda9304b03c68a3563b75fc8f92bf951e335afb289353dc249e82926178eac7ded78ae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;bb6881874825e60e1160416d6c426eae65f2459ef951e335afb289353dc249e82926178eac7ded78ae8535c23afedda9304b03c68a3563b75fc8f92b0000000000000000000005a0;6810e776880c02933d47db1b9fc05908e5386b96def1ca1fb7fbcdc777520aa7f396b4e015f497ab92762b42a06dcdddc5b7362cfb01e631c4d44b40000200000000000000000182;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2fd0205066521550d7d7ab19da8f72bb004b4c3419232a548dd9e81bac65500b5e0d918f8ba93675c000200000000000000000423;0fe906e030a44ef24ca8c7dc7b7c53a6c4f00ce977146784315ba81904d654466968e3a7c196d1f3daba3d8ccf79ef289a7e2dbce51871b39ea445a2;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2dbdb4d16eda451d0503b854cf79d55697f90c8df1535d7ca00323aa32bd62aeddf7ca651e4b95966;4cbde5c4b4b53ebe4af4adb85404725985406163a35b1b31ce002fbf2058d22f30f95d405200a15b4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;4cbde5c4b4b53ebe4af4adb85404725985406163bb6881874825e60e1160416d6c426eae65f2459e4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;a35b1b31ce002fbf2058d22f30f95d405200a15bbb6881874825e60e1160416d6c426eae65f2459e4cbde5c4b4b53ebe4af4adb85404725985406163000000000000000000000595;79c71d3436f39ce382d0f58f1b011d88100b9d91c02aaa39b223fe8d0a0e5c4f27ead9083c756cc21bccaac02bae336c6352acc3b772059ef1142fa70002000000000000000001f0;68917a0e538cf4a807b3d415c1af5cdbab0ff4dca0b86991c6218b36c1d19d4a2e9eb0ce3606eb4848995dbdca50fa5346b0771d40a5ae7664262f7e;7bc3485026ac48b6cf9baf0a377477fff5703af8c71ea051a5f82c67adcf634c36ffe6334793d24c85b2b559bc2d21104c4defdd6efca8a20343361d;7bc3485026ac48b6cf9baf0a377477fff5703af8d4fa2d31b7968e448877f69a96de69f5de8cd23e85b2b559bc2d21104c4defdd6efca8a20343361d;c71ea051a5f82c67adcf634c36ffe6334793d24cd4fa2d31b7968e448877f69a96de69f5de8cd23e85b2b559bc2d21104c4defdd6efca8a20343361d;a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48c02aaa39b223fe8d0a0e5c4f27ead9083c756cc296646936b91d6b9d7d0c47c496afbf3d6ec7b6f8000200000000000000000019;2260fac5e5542a773aa44fbcfedf7c193bc2c599eb4c2781e4eba804ce9a9803c67d0893436bb27dfeadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;2260fac5e5542a773aa44fbcfedf7c193bc2c599fe18be6b3bd88a2d2a7f928d00292e7a9963cfc6feadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;eb4c2781e4eba804ce9a9803c67d0893436bb27dfe18be6b3bd88a2d2a7f928d00292e7a9963cfc6feadd389a5c427952d8fdb8057d6c8ba1156cc56000000000000000000000066;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2cfeaead4947f0705a14ec42ac3d44129e1ef3ed55122e01d819e58bb2e22528c0d68d310f0aa6fd7000200000000000000000163;9f8f72aa9304c8b593d555f12ef6589cc3a579a2c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2aac98ee71d4f8a156b6abaa6844cdb7789d086ce00020000000000000000001b;1cf0f3aabe4d12106b27ab44df5473974279c524c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2ea39581977325c0833694d51656316ef8a926a62000200000000000000000036;6b175474e89094c44da98b954eedeac495271d0fc02aaa39b223fe8d0a0e5c4f27ead9083c756cc20b09dea16768f0799065c475be02919503cb2a3500020000000000000000001a;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f8353157092ed8be69a9df8f95af097bbf33cb2af8353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2fa0b86991c6218b36c1d19d4a2e9eb0ce3606eb488353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2fdac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;8353157092ed8be69a9df8f95af097bbf33cb2afa0b86991c6218b36c1d19d4a2e9eb0ce3606eb488353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;8353157092ed8be69a9df8f95af097bbf33cb2afdac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48dac17f958d2ee523a2206206994597c13d831ec78353157092ed8be69a9df8f95af097bbf33cb2af0000000000000000000005d9;3839a0dd920463eb5d8231efe4d8c5edc44145ecd4fa2d31b7968e448877f69a96de69f5de8cd23e51cdf9cc199f8121b58d9337983a79a1b87330fd;c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2ec53bf9167f50cdeb3ae105f56099aaab9061f83bda917a67c7d9ae67da92c4ea87e10e5d6c11b54;4ba01f22827018b4772cd326c7627fb4956a7c00890a5122aa1da30fec4286de7904ff808f0bd74a9054ae85300c7d3a325714fc2f1454d0b7c73a12;3c640f0d3036ad85afa2d5a9e32be651657b874f50cf90b954958480b8df7958a9e965752f62712450cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;3c640f0d3036ad85afa2d5a9e32be651657b874fd4e7c1f3da1144c9e2cfd1b015eda7652b4a439950cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;3c640f0d3036ad85afa2d5a9e32be651657b874feb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;50cf90b954958480b8df7958a9e965752f627124d4e7c1f3da1144c9e2cfd1b015eda7652b4a439950cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;50cf90b954958480b8df7958a9e965752f627124eb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;d4e7c1f3da1144c9e2cfd1b015eda7652b4a4399eb486af868aeb3b6e53066abc9623b1041b42bc050cf90b954958480b8df7958a9e965752f62712400000000000000000000046f;35e78b3982e87ecfd5b3f3265b601c046cdbe232a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48f506984c16737b1a9577cadeda02a49fd612aff80002000000000000000002a9;6c0aeceedc55c9d55d8b99216a670d85330941c3c02aaa39b223fe8d0a0e5c4f27ead9083c756cc21846c6cbe0d433e152fa358e5ff27968e18bce7c;44108f0223a3c3028f5fe7aec7f9bb2e66bef82f7f39c581f595b53c5cb19bd0b3f8da6c935e2ca036be1e97ea98ab43b4debf92742517266f5731a3000200000000000000000466;c0c17dd08263c16f6b64e772fb9b723bf1344ddfe108fbc04852b5df72f9e44d7c29f47e7a993adde00e947decfe01692070e113002705bdf77ddbd3;a3931d71877c0e7a3148cb7eb4463524fec27fbdf3b5b661b92b75c71fa5aba8fd95d7514a9cd605642bb6860b4776cc10b26b8f361fd139e7f0db04;97ccc1c046d067ab945d3cf3cc6920d3b1e54c88d4fa2d31b7968e448877f69a96de69f5de8cd23e114907c2a07978c38ebb9f9f6a5261a846b79521'
_BAL_MAP = {}

def _dl_bal_pool(tin, tout):
    """poolId (0x..) of a Balancer pool holding BOTH tokens, else None. Lazily indexes."""
    if not _BAL_MAP:
        for r in _BAL_TBL.split(';'):
            if len(r) >= 144:
                _BAL_MAP[r[:80]] = '0x' + r[80:144]
    a, b = sorted([tin.lower()[2:], tout.lower()[2:]])
    return _BAL_MAP.get(a + b)

def _dl_bal_quote(url, tin, tout, amt, pid):
    """Exact out via Vault.queryBatchSwap (GIVEN_IN). Returns int (0 on failure).
    Deltas come back as int256[]: [+amountIn, -amountOut] -> out = -deltas[1]."""

    def _dz62(amt, pid, tin, tout, url):
        sig = 'queryBatchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],address[],(address,bool,address,bool))'
        z = '0x0000000000000000000000000000000000000000'
        data = _dl_sel(sig) + encode(['uint8', '(bytes32,uint256,uint256,uint256,bytes)[]', 'address[]', '(address,bool,address,bool)'], [0, [(bytes.fromhex(pid[2:]), 0, 1, int(amt), b'')], [tin, tout], (z, False, z, False)]).hex()
        r = _dl_ethcall(url, _BAL_VAULT, data)
        return (data, r, sig, z)
    from eth_abi import encode
    data, r, sig, z = _dz62(amt, pid, tin, tout, url)
    if not r or len(r) < 258:
        return 0
    d = int(r[194:258], 16)
    if d >= 2 ** 255:
        d -= 2 ** 256
    return -d if d < 0 else 0

def _dl_bal_ix(tin, tout, amt, recipient, pid):
    """approve + Vault.swap interactions for a single-pool Balancer swap."""

    def _dz61():
        sig = 'swap((bytes32,uint8,address,address,uint256,bytes),(address,bool,address,bool),uint256,uint256)'
        swap = _dl_sel(sig) + encode(['(bytes32,uint8,address,address,uint256,bytes)', '(address,bool,address,bool)', 'uint256', 'uint256'], [(bytes.fromhex(pid[2:]), 0, tin, tout, amt, b''), (recipient, False, recipient, False), 1, 9999999999]).hex()
        return ([(tin, approve), (_BAL_VAULT, swap)],)
        return _DR_UNSET
    from eth_abi import encode
    amt = int(amt)
    approve = '0x095ea7b3' + _BAL_VAULT[2:].rjust(64, '0').lower() + amt.to_bytes(32, 'big').hex()
    _r_dz61 = _dz61()
    if _r_dz61 is not _DR_UNSET:
        return _r_dz61[0]

def _dl_eth_ix(tin, tout, amt, recipient, route, min_out=1):

    def _dz59():
        if kind == 'bal':
            return (_dl_bal_ix(tin, tout, amt, recipient, route[1][1]),)
        return _DR_UNSET

    def _dz58(route):
        tokens, fees = (route[1][1], route[1][2])
        _dz55()
        return (fees, tokens)

    def _dz57(amt, mo, recipient, route, tin, tout):
        fee = route[1][1]
        swap = _dl_sel('exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))') + encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(tin, tout, int(fee), recipient, 9999999999, amt, mo, 0)]).hex()
        return (fee, swap)

    def _dz56(amt, min_out, route):
        amt = int(amt)
        mo = int(min_out)
        approve = '0x095ea7b3' + _ETH_ROUTER[2:].rjust(64, '0').lower() + amt.to_bytes(32, 'big').hex()
        kind = route[1][0]
        return (amt, approve, kind, mo)

    def _dz55():
        nonlocal swap
        b = b''
        for i, t in enumerate(tokens):
            b += bytes.fromhex(t[2:])
            if i < len(fees):
                b += int(fees[i]).to_bytes(3, 'big')
        swap = _dl_sel('exactInput((bytes,address,uint256,uint256,uint256))') + encode(['(bytes,address,uint256,uint256,uint256)'], [(b, recipient, 9999999999, amt, mo)]).hex()
    from eth_abi import encode
    amt, approve, kind, mo = _dz56(amt, min_out, route)
    _r_dz59 = _dz59()
    if _r_dz59 is not _DR_UNSET:
        return _r_dz59[0]
    if kind == 'single':
        fee, swap = _dz57(amt, mo, recipient, route, tin, tout)
    else:
        fees, tokens = _dz58(route)
    return [(tin, approve), (_ETH_ROUTER, swap)]
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

    def _dz54():
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
        _r_dz54 = _dz54()
        if _r_dz54 is not _DR_UNSET:
            return _r_dz54[0]
    return None

def _dl_flatten(ix):
    """Interaction calldatas, unwrapping one level of multicall(bytes[])."""

    def _dz53():
        if cd[:8] in _SEL_MC:
            try:
                payload = bytes.fromhex(cd[8:])
                calls = decode(['bytes[]'], payload[32:] if cd[:8] == '5ae401dc' else payload)[0]
                for c in calls:
                    h = c.hex()
                    if len(h) >= 8:
                        flat.append(h)
            except Exception:
                flat.append(cd)
        else:
            flat.append(cd)
    from eth_abi import decode
    datas = []
    for i in ix:
        cd = str(getattr(i, 'call_data', getattr(i, 'calldata', '')) or '')
        if cd.startswith('0x'):
            cd = cd[2:]
        if len(cd) >= 8:
            datas.append(cd)
    flat = []
    for cd in datas:
        _dz53()
    return flat

def _dl_decode_path(body, sel, url):
    """Re-quote a decoded exactInput (path) champion swap."""

    def _dz52(body, sel):
        path, _rec, amt, _mo = decode(['(bytes,address,uint256,uint256)'], body)[0] if sel == _SEL_EI_02 else decode(['(bytes,address,uint256,uint256,uint256)'], body)[0][:4]
        toks, fees = ([], [])
        p = path if isinstance(path, (bytes, bytearray)) else bytes.fromhex(str(path))
        return (_mo, _rec, amt, fees, p, path, toks)

    def _dz51():
        o = 0
        while o + 20 <= len(p):
            toks.append('0x' + p[o:o + 20].hex())
            o += 20
            if o + 3 <= len(p):
                fees.append(int.from_bytes(p[o:o + 3], 'big'))
                o += 3
        return (_dl_qpath(url, toks, fees, amt),)
        return _DR_UNSET
    from eth_abi import decode
    _mo, _rec, amt, fees, p, path, toks = _dz52(body, sel)
    _r_dz51 = _dz51()
    if _r_dz51 is not _DR_UNSET:
        return _r_dz51[0]

def _dl_decode_one(cd, url, target=None):
    """Decode+re-quote one calldata. Returns ('ANSWER', q_or_None) if it's a swap we
    recognize — UniV3 exactInput(Single), Curve exchange, or UniV2 — (q>0 -> its output;
    else None so caller DEFERS, never treats as blind), ('SWAP', None) if a swap is present
    but undecodable, or ('SKIP', None). `target` = the interaction's contract (the exotic
    venue's router), used to re-quote Curve/UniV2 against the exact router the king used."""

    def _dz50(cd):
        sel = cd[:8]
        body = bytes.fromhex(cd[8:]) if len(cd) > 8 else b''
        return (body, sel)

    def _dz49(body, url):
        tin, tout, fee, _r, amt, _m, _s = decode(['(address,address,uint24,address,uint256,uint256,uint160)'], body)[0]
        q = _dl_qsingle(url, tin, tout, amt, fee)
        return (_m, _r, _s, amt, fee, q, tin, tout)

    def _dz48():
        nonlocal q
        _r_dz47 = _dz47()
        if _r_dz47 is not _DR_UNSET:
            return (_r_dz47[0],)
        if sel in _SEL_UNIV2:
            q = _dl_univ2_requote(url, target, cd)
            return (('ANSWER', q if q > 0 else None),)
        return _DR_UNSET

    def _dz47():
        nonlocal _m, _r, _s, amt, fee, q, tin, tout
        if sel == _SEL_EIS:
            tin, tout, fee, _r, _d, amt, _m, _s = decode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], body)[0]
            q = _dl_qsingle(url, tin, tout, amt, fee)
            return (('ANSWER', q if q > 0 else None),)
        _r_dz46 = _dz46()
        if _r_dz46 is not _DR_UNSET:
            return (_r_dz46[0],)
        return _DR_UNSET

    def _dz46():
        nonlocal q
        if sel in (_SEL_EI_02, _SEL_EI):
            q = _dl_decode_path(body, sel, url)
            return (('ANSWER', q if q > 0 else None),)
        if sel == _SEL_CURVE_EX:
            q = _dl_curve_requote(url, target, cd)
            return (('ANSWER', q if q > 0 else None),)
        return _DR_UNSET
    from eth_abi import decode
    body, sel = _dz50(cd)
    try:
        if sel == _SEL_EIS_02:
            _m, _r, _s, amt, fee, q, tin, tout = _dz49(body, url)
            return ('ANSWER', q if q > 0 else None)
        _r_dz48 = _dz48()
        if _r_dz48 is not _DR_UNSET:
            return _r_dz48[0]
    except Exception:
        return ('SWAP', None)
    return ('SKIP', None)

def _dl_v2c():
    return ('0x45312ea0eFf7E09C83CBE249fa1d7598c4C8cd4e', 'c872a3c5', '81889a2c', ('5c11d795', '38ed1739'), 'd06ca61f', '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D')
_DL_CURVE_RTR, _SEL_CURVE_EX, _SEL_CURVE_DY, _SEL_UNIV2, _SEL_GAO, _DL_UNIV2_RTR = _dl_v2c()

def _dl_curve_requote(url, router, cd):
    """Re-quote the king's CurveRouterNG.exchange calldata via get_dy with its OWN
    route[11]/swap[5][5]/amount -> the king's real Curve output (0 on failure)."""

    def _dz45(cd):
        d = decode(['address[11]', 'uint256[5][5]', 'uint256', 'uint256', 'address[5]', 'address'], bytes.fromhex(cd[8:]))
        route, swap, amt = (d[0], d[1], int(d[2]))
        return (amt, d, route, swap)

    def _dz44():
        data = '0x' + _SEL_CURVE_DY + encode(['address[11]', 'uint256[5][5]', 'uint256'], [list(route), [list(s) for s in swap], amt]).hex()
        q = _dl_ethcall(url, r, data)
        return (int(q[2:66], 16) if q and len(q) >= 66 else 0,)
        return _DR_UNSET
    from eth_abi import decode, encode
    try:
        amt, d, route, swap = _dz45(cd)
    except Exception:
        return 0
    r = router if router and router.startswith('0x') and (len(router) == 42) else _DL_CURVE_RTR
    _r_dz44 = _dz44()
    if _r_dz44 is not _DR_UNSET:
        return _r_dz44[0]

def _dl_univ2_requote(url, router, cd):
    """Re-quote the king's UniV2 swapExactTokensForTokens* calldata via getAmountsOut
    with its OWN (amountIn, path) -> the king's real UniV2 output (0 on failure)."""

    def _dz43(amt, path, router):
        r = router if router and router.startswith('0x') and (len(router) == 42) else _DL_UNIV2_RTR
        data = '0x' + _SEL_GAO + encode(['uint256', 'address[]'], [int(amt), list(path)]).hex()
        _r_dz42 = _dz42()
        return (_r_dz42, data, r)

    def _dz42():
        q = _dl_ethcall(url, r, data)
        if not q or len(q) < 66:
            return (0,)
        try:
            arr = decode(['uint256[]'], bytes.fromhex(q[2:]))[0]
            return (int(arr[-1]) if len(arr) else 0,)
        except Exception:
            return (0,)
        return _DR_UNSET
    from eth_abi import decode, encode
    try:
        amt, _mo, path, _to, _dl = decode(['uint256', 'uint256', 'address[]', 'address', 'uint256'], bytes.fromhex(cd[8:]))
    except Exception:
        return 0
    _r_dz42, data, r = _dz43(amt, path, router)
    if _r_dz42 is not _DR_UNSET:
        return _r_dz42[0]

def _dz63():
    _XC_CANON = {'weth': {1: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 8453: '0x4200000000000000000000000000000000000006'}, 'usdc': {1: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 8453: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'}}
    _XC_ROUTER = {1: '0xE592427A0AEce92De3Edee1F18E0157C05861564', 8453: '0x2626664c2603336E57B271c5C0b26F421741e481'}
    _XC_ANVIL = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'
    return (_XC_CANON, _XC_ROUTER, _XC_ANVIL)
_XC_CANON, _XC_ROUTER, _XC_ANVIL = _dz63()

def _xc_class(token):
    t = str(token or '').lower()
    for cls, by in _XC_CANON.items():
        if any((a.lower() == t for a in by.values())):
            return cls
    return None

def _xc_approve(spender, amt):
    return '0x095ea7b3' + spender[2:].lower().rjust(64, '0') + int(amt).to_bytes(32, 'big').hex()

def _xc_transfer(to, amt):
    return '0xa9059cbb' + to[2:].lower().rjust(64, '0') + int(amt).to_bytes(32, 'big').hex()

def _xc_swap(chain, tin, tout, fee, recip, amt):
    from eth_abi import encode
    if int(chain) == 8453:
        s = _dl_sel('exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))')
        body = encode(['(address,address,uint24,address,uint256,uint256,uint160)'], [(tin, tout, int(fee), recip, int(amt), 0, 0)]).hex()
    else:
        s = _dl_sel('exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))')
        body = encode(['(address,address,uint24,address,uint256,uint256,uint256,uint160)'], [(tin, tout, int(fee), recip, 9999999999, int(amt), 0, 0)]).hex()
    return s + body