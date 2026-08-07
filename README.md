# Cover-extended DEX intent solver

Routes Base/Ethereum swap intents, with an additional Curve StableSwap cover for
pairs that carry no Uniswap or Aerodrome pool.

## Design

- the routing stack resolves each intent to a venue and builds its calldata
- `cover_ext.py` adds Curve StableSwap discovery through the MetaRegistry, used
  only where the primary stack returns no plan at all

## Behaviour

For every order the incumbent serves, this solver targets the same delivered
output within the relative-scoring match band, and never returns an empty plan
where a route exists.
