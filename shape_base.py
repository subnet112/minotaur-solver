_DR_UNSET = object()
import shape_lib as _sl

def _pair_reserves(w3, pair):

    def _dz2417(pair, w3):
        res = _dec(['uint112', 'uint112', 'uint32'], w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}))
        return res
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    res = _dz2417(pair, w3)
    return (int(res[0]), int(res[1]))

def base_out_av2(s, plan, spec, tin, tout, amt, chain_id):
    """Re-quote the champion's OWN aero+UR 2-leg route: decode-VERIFIED
against the baked route spec (any mismatch -> None = defer); leg1 via the
plan's own aero router getAmountsOut, leg2 via the V2 pair's reserves."""
    try:
        from eth_abi import decode as _dec, encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck

        def _dr331():

            def _dz2416():
                ixs = [i for i in plan.interactions if not str(i.call_data).lower().startswith('0x095ea7b3')]
                _r_dz2415 = _dz2415()
                return (_r_dz2415, ixs)

            def _dz2415():
                if len(ixs) != 2 or ixs[0].call_data[:10] != '0xcac88ea9' or ixs[1].call_data[:10] != '0x3593564c':
                    return (None,)
                return _DR_UNSET
            _r_dz2415, ixs = _dz2416()
            if _r_dz2415 is not _DR_UNSET:
                return _r_dz2415[0]
            return ixs

        def _dr332(cd1):

            def _dz2413(cd1):
                amt_in, _mo, routes, _to, _dl = _dec(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], bytes.fromhex(cd1[10:]))
                return (_dl, _mo, _to, amt_in, routes)
            _dl, _mo, _to, amt_in, routes = _dz2413(cd1)
            if len(routes) != 1 or routes[0][0].lower() != tin.lower() or routes[0][1].lower() != spec['base_mid'] or (int(amt_in) != int(amt)) or routes[0][2]:
                return False
            return True

        def _dr333(cd2):

            def _dz2411(inputs):
                _r, _ai, _mo2, path, _p = _dec(['address', 'uint256', 'uint256', 'address[]', 'bool'], inputs[0])
                _r_dz2410 = _dz2410()
                return (_ai, _mo2, _p, _r, _r_dz2410, path)

            def _dz2410():
                return ([p.lower() for p in path] == [spec['base_mid'], tout.lower()],)
                return _DR_UNSET

            def _dz2409(cd2):
                cmds, inputs, _d2 = _dec(['bytes', 'bytes[]', 'uint256'], bytes.fromhex(cd2[10:]))
                return (_d2, cmds, inputs)
            _d2, cmds, inputs = _dz2409(cd2)
            if cmds.hex() != '08' or len(inputs) != 1:
                return False
            _ai, _mo2, _p, _r, _r_dz2410, path = _dz2411(inputs)
            if _r_dz2410 is not _DR_UNSET:
                return _r_dz2410[0]

        def _dr334(w3, aero_router):

            def _dz2407():
                return (_dec(['uint256[]'], w3.eth.call({'to': _ck(aero_router), 'data': '0x' + (gao + pay).hex()}))[0][-1],)
                return _DR_UNSET
            gao = _keccak(text='getAmountsOut(uint256,(address,address,bool,address)[])')[:4]
            pay = _enc(['uint256', '(address,address,bool,address)[]'], [int(amt), [(_ck(tin), _ck(spec['base_mid']), False, '0x0000000000000000000000000000000000000000')]])
            _r_dz2407 = _dz2407()
            if _r_dz2407 is not _DR_UNSET:
                return _r_dz2407[0]

        def _dr335(w3, q1):

            def _dz2405():
                ai = int(q1) * 997
                return (ai * rout // (rin * 1000 + ai) or None,)
                return _DR_UNSET
            res = _pair_reserves(w3, spec['base_pair'])
            rin, rout = (res[0], res[1]) if spec.get('base_mid_is_t0') else (res[1], res[0])
            _r_dz2405 = _dz2405()
            if _r_dz2405 is not _DR_UNSET:
                return _r_dz2405[0]

        def _dr336():

            def _dz2403():
                w3 = s._get_web3(int(chain_id))
                _r_dz2401 = _dz2401()
                return (_r_dz2401, w3)

            def _dz2402():
                if not ixs or not _dr332(ixs[0].call_data) or (not _dr333(ixs[1].call_data)):
                    return (None,)
                return _DR_UNSET

            def _dz2401():
                if w3 is None:
                    return (None,)
                q1 = _dr334(w3, ixs[0].target)
                return (_dr335(w3, q1) if q1 else None,)
                return _DR_UNSET
            ixs = _dr331()
            _r_dz2402 = _dz2402()
            if _r_dz2402 is not _DR_UNSET:
                return _r_dz2402[0]
            _r_dz2401, w3 = _dz2403()
            if _r_dz2401 is not _DR_UNSET:
                return _r_dz2401[0]
        return _dr336()
    except Exception:
        return None

def base_out(s, plan, chain_id):
    """Re-quote the BASE plan's OWN single-venue route live (uni router02
7-field / pancake smart-router 8-field exactInputSingle). None for splits,
multi-leg or unknown venues (a healthy base) -> the caller DEFERS. This is
the champion-route gate: overrides compare against what the base plan
actually delivers at this block, never a guessed alternative."""
    try:

        def _dr300():

            def _dz2399(it):
                cd = str(getattr(it, 'call_data', '') or '')
                body = cd[2:] if cd.startswith('0x') else cd
                return (body, cd)

            def _dz293():
                swaps.append((str(getattr(it, 'target', '') or '').lower(), body[:8].lower(), body[8:]))
            swaps = []
            for it in getattr(plan, 'interactions', None) or []:
                body, cd = _dz2399(it)
                if len(body) < 8 or body[:8].lower() == '095ea7b3':
                    continue
                _dz293()
            return swaps
        swaps = _dr300()
        if len(swaps) != 1:
            return None
        target, sel, args = swaps[0]

        def _dr301():

            def _dz2398():
                if _r_dz2397 is not _DR_UNSET:
                    return (_r_dz2397[0],)
                if sel == '414bf389':
                    _r_dz2396 = _dz2396()
                    if _r_dz2396 is not _DR_UNSET:
                        return (_r_dz2396[0],)
                return (None,)
                return _DR_UNSET

            def _dz2397():
                if sel == '04e45aaf':
                    return (s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': _w(2), 'mid': _a(1)}, _a(0), _w(4), chain_id),)
                return _DR_UNSET

            def _dz2396():
                rtr = 'pancake' if target == '0x1b81d678ffb9c0263b24a97847620c99d213eb14' else 'uni'
                return (s._hydra_quote_leg1({'leg1_router': rtr, 'leg1_fee': _w(2), 'mid': _a(1)}, _a(0), _w(5), chain_id),)
                return _DR_UNSET

            def _w(i):
                return int(args[i * 64:(i + 1) * 64], 16)

            def _a(i):
                return '0x' + args[i * 64 + 24:(i + 1) * 64]
            _r_dz2397 = _dz2397()
            _r_dz2398 = _dz2398()
            if _r_dz2398 is not _DR_UNSET:
                return _r_dz2398[0]
        return _dr301()
    except Exception:
        return None