__all__ = ['_fx_89']

def _fx_89(_B1Ix, _B1Plan, _B1_ROUTER_8453, _b1_approve, _b1_encode_exact_input_base, _b1_encode_path, _b1_v3single, _b1time, amount_in, amount_out_min_floor, dir_fee, dir_out, fees, hub_out, intent, state, tin, tokens, tout):
    if max(hub_out, dir_out) <= 0:
        return None
    floor = int(amount_out_min_floor)
    if floor > 0 and max(hub_out, dir_out) < floor:
        return None
    recipient = getattr(state, 'contract_address', '') or getattr(state, 'owner', '')

    def _fx_81():
        chain_id = int(getattr(state, 'chain_id', 0) or 0)
        deadline = int(_b1time.time()) + 300
        if hub_out >= dir_out:
            swap_cd = _b1_encode_exact_input_base(_b1_encode_path(tokens, fees), recipient, amount_in, floor)
            route = 'tabled ' + '->'.join((_t[:6] for _t in tokens)) + f' fees={fees}'
        else:
            swap_cd = _b1_v3single(token_in=tin, token_out=tout, fee=dir_fee, recipient=recipient, deadline=deadline, amount_in=amount_in, amount_out_minimum=floor, chain_id=chain_id)
            route = f'direct fee={dir_fee}'
        return (chain_id, deadline, route, swap_cd)
    chain_id, deadline, route, swap_cd = _fx_81()
    return _B1Plan(intent_id=intent.app_id, interactions=[_B1Ix(target=tin, value='0', call_data=_b1_approve(_B1_ROUTER_8453, amount_in), chain_id=chain_id), _B1Ix(target=_B1_ROUTER_8453, value='0', call_data=swap_cd, chain_id=chain_id)], deadline=deadline, nonce=getattr(state, 'nonce', 0), metadata={'solver': 'b1-route', 'route': route})