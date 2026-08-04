# pymsno-lean

A standalone Minotaur SN112 solver — deliberately not a fork of the reigning
champion.

`generate_plan` serves, in order:

1. a frozen delivery-verified plan for the exact order shape, if held; else
2. the better of a UniswapV3 (best fee tier via QuoterV2) and a UniswapV2
   (getAmountsOut) route, delivering to the app contract.

Every path fails closed to `None` rather than emitting an unverified guess.
