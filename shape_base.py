import shape_lib as _sl

def _pair_reserves(w3, pair):
    from eth_abi import decode as _dec
    from eth_utils import keccak as _keccak, to_checksum_address as _ck
    res = _dec(['uint112', 'uint112', 'uint32'], w3.eth.call({'to': _ck(pair), 'data': '0x' + _keccak(text='getReserves()')[:4].hex()}))
    return (int(res[0]), int(res[1]))

def base_out_av2(s, plan, spec, tin, tout, amt, chain_id):
    """Re-quote the champion's OWN aero+UR 2-leg route: decode-VERIFIED
against the baked route spec (any mismatch -> None = defer); leg1 via the
plan's own aero router getAmountsOut, leg2 via the V2 pair's reserves."""
    try:
        from eth_abi import decode as _dec, encode as _enc
        from eth_utils import keccak as _keccak, to_checksum_address as _ck

        def _dr331():
            ixs = [i for i in plan.interactions if not str(i.call_data).lower().startswith('0x095ea7b3')]
            if len(ixs) != 2 or ixs[0].call_data[:10] != '0xcac88ea9' or ixs[1].call_data[:10] != '0x3593564c':
                return None
            return ixs

        def _dr332(cd1):
            amt_in, _mo, routes, _to, _dl = _dec(['uint256', 'uint256', '(address,address,bool,address)[]', 'address', 'uint256'], bytes.fromhex(cd1[10:]))

            def _fw1():
                if len(routes) != 1 or routes[0][0].lower() != tin.lower() or routes[0][1].lower() != spec['base_mid'] or (int(amt_in) != int(amt)) or routes[0][2]:
                    return (False,)
                return (True,)
            _fwr1 = _fw1()
            if _fwr1 is not None:
                return _fwr1[0]

        def _dr333(cd2):
            cmds, inputs, _d2 = _dec(['bytes', 'bytes[]', 'uint256'], bytes.fromhex(cd2[10:]))
            if cmds.hex() != '08' or len(inputs) != 1:
                return False
            _r, _ai, _mo2, path, _p = _dec(['address', 'uint256', 'uint256', 'address[]', 'bool'], inputs[0])
            return [p.lower() for p in path] == [spec['base_mid'], tout.lower()]

        def _dr334(w3, aero_router):
            gao = _keccak(text='getAmountsOut(uint256,(address,address,bool,address)[])')[:4]
            pay = _enc(['uint256', '(address,address,bool,address)[]'], [int(amt), [(_ck(tin), _ck(spec['base_mid']), False, '0x0000000000000000000000000000000000000000')]])
            return _dec(['uint256[]'], w3.eth.call({'to': _ck(aero_router), 'data': '0x' + (gao + pay).hex()}))[0][-1]

        def _dr335(w3, q1):
            res = _pair_reserves(w3, spec['base_pair'])
            rin, rout = (res[0], res[1]) if spec.get('base_mid_is_t0') else (res[1], res[0])
            ai = int(q1) * 997
            return ai * rout // (rin * 1000 + ai) or None

        def _dr336():
            ixs = _dr331()
            if not ixs or not _dr332(ixs[0].call_data) or (not _dr333(ixs[1].call_data)):
                return None
            w3 = s._get_web3(int(chain_id))
            if w3 is None:
                return None
            q1 = _dr334(w3, ixs[0].target)
            return _dr335(w3, q1) if q1 else None
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
            swaps = []
            for it in getattr(plan, 'interactions', None) or []:
                cd = str(getattr(it, 'call_data', '') or '')

                def _fw1():
                    body = cd[2:] if cd.startswith('0x') else cd
                    if len(body) < 8 or body[:8].lower() == '095ea7b3':
                        return ('c',)
                    swaps.append((str(getattr(it, 'target', '') or '').lower(), body[:8].lower(), body[8:]))
                if _fw1() is not None:
                    continue
            return swaps
        swaps = _dr300()
        if len(swaps) != 1:
            return None
        target, sel, args = swaps[0]

        def _dr301():

            def _w(i):
                return int(args[i * 64:(i + 1) * 64], 16)

            def _a(i):
                return '0x' + args[i * 64 + 24:(i + 1) * 64]
            if sel == '04e45aaf':
                return s._hydra_quote_leg1({'leg1_router': 'uni', 'leg1_fee': _w(2), 'mid': _a(1)}, _a(0), _w(4), chain_id)
            if sel == '414bf389':
                rtr = 'pancake' if target == '0x1b81d678ffb9c0263b24a97847620c99d213eb14' else 'uni'
                return s._hydra_quote_leg1({'leg1_router': rtr, 'leg1_fee': _w(2), 'mid': _a(1)}, _a(0), _w(5), chain_id)
            return None
        return _dr301()
    except Exception:
        return None