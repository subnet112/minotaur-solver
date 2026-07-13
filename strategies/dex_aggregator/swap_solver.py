"""Default swap intent solver -- the baseline miners must beat.

This processor handles "swap" intent types by building Uniswap V3
single-hop execution plans. It serves as a reference implementation
and functional baseline. Miners are expected to surpass it with:

- Smarter routing (multi-hop, cross-DEX, aggregation)
- MEV protection (private mempools, flashbots)
- Better slippage estimation
- Cross-chain routing
- Dynamic fee tier selection
- ML-based parameter tuning from score feedback

Intent metadata format for swaps::

    {
        "input_token": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "output_token": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "input_amount": "1000000000",       # in token's smallest unit
        "min_output_amount": "500000000",   # minimum acceptable output
        "recipient": "0x...",               # optional, defaults to contract address
        "fee_tier": 3000,                   # optional, defaults to 3000
    }
"""

from __future__ import annotations

import logging
from typing import Any

from minotaur_subnet.shared.types import (
    AppIntentDefinition,
    ExecutionPlan,
    Interaction,
    IntentState,
    ScoreResult,
)

from common.abi_utils import encode_approve
from strategies.dex_aggregator.v3_codec import encode_exact_input_single
from minotaur_subnet.sdk.intent_processor import IntentProcessor
from minotaur_subnet.sdk.processor_context import ProcessorContext
from minotaur_subnet.v3.contexts import SwapIntentContext
from minotaur_subnet.v3.manifest import manifest_from_definition, normalize_swap_intent_params

logger = logging.getLogger(__name__)

# Well-known Uniswap V3 SwapRouter addresses per chain
UNISWAP_V3_ROUTERS: dict[int, str] = {
    1: "0xE592427A0AEce92De3Edee1F18E0157C05861564",       # Ethereum mainnet
    8453: "0x2626664c2603336E57B271c5C0b26F421741e481",    # Base (SwapRouter02)
    964: "0x667A1AA098D03f788eBaD7678B7c02504EaC6092",     # Bittensor EVM (Astrid Bridge SwapRouter V1, with deadline)
    31337: "0xE592427A0AEce92De3Edee1F18E0157C05861564",   # Anvil mainnet fork
}

# Default fee tier: 0.3% (3000 hundredths of a bip)
DEFAULT_FEE_TIER = 3000

# Default deadline offset: 5 minutes
DEFAULT_DEADLINE_OFFSET = 300

# Default slippage tolerance: 0.5%
DEFAULT_SLIPPAGE_BPS = 50


def _state_params(state: IntentState) -> dict[str, Any]:
    typed = getattr(state, "typed_context", None)
    if typed is not None:
        raw = getattr(typed, "raw_params", None)
        if isinstance(raw, dict):
            return raw
    return state.raw_params_view()


def _intent_function_from_state(state: IntentState, default: str = "swap") -> str:
    typed = getattr(state, "typed_context", None)
    params = _state_params(state)
    return (
        getattr(typed, "intent_function", "")
        or state.control_view().get("_intent_function")
        or params.get("intent_function")
        or default
    )


class SwapIntentProcessor(IntentProcessor):
    """Default swap solver -- finds optimal single-hop swap routes.

    This is the baseline implementation that ships with the SDK. It
    produces valid Uniswap V3 exactInputSingle execution plans with
    proper ERC-20 approvals.

    Miners should beat this by implementing:
    - Multi-hop routing through intermediate tokens
    - Cross-DEX price comparison
    - Dynamic fee tier selection based on liquidity
    - Price impact estimation and split routing
    - Score-based parameter tuning via on_score_received
    """

    def __init__(
        self,
        default_fee_tier: int = DEFAULT_FEE_TIER,
        deadline_offset: int = DEFAULT_DEADLINE_OFFSET,
        slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    ) -> None:
        """Initialize the swap solver.

        Args:
            default_fee_tier: Default Uniswap V3 pool fee tier in hundredths
                of a bip. Common values: 100 (0.01%), 500 (0.05%),
                3000 (0.3%), 10000 (1%).
            deadline_offset: Seconds from current timestamp to set as the
                transaction deadline.
            slippage_bps: Slippage tolerance in basis points. Applied to
                min_output_amount if not explicitly provided in the intent.
        """
        self.default_fee_tier = default_fee_tier
        self.deadline_offset = deadline_offset
        self.slippage_bps = slippage_bps

    def supported_intent_types(self) -> list[str]:
        """This processor handles swap intents."""
        return ["swap"]

    async def generate_plan(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
        context: ProcessorContext,
    ) -> ExecutionPlan:
        """Generate a swap execution plan via Uniswap V3 exactInputSingle.

        Strategy (baseline):
        1. Parse intent metadata for input/output tokens and amounts
        2. Resolve the Uniswap V3 router for the target chain
        3. Build approve + swap interactions
        4. Return the execution plan

        Args:
            intent: App Intent definition. The ``config`` field's
                ``supported_chains`` determines the target chain, and
                intent metadata (stored in ``description`` or passed via
                the intent state's ``raw_params``) provides swap parameters.
            state: On-chain state of the intent contract.
            context: Execution context with chain info, prices, and config.

        Returns:
            ExecutionPlan with approve + exactInputSingle interactions.

        Raises:
            ValueError: If required metadata is missing or chain unsupported.
        """
        # Extract swap parameters from structured runtime params
        params = self._extract_swap_params(intent, state)

        input_token: str = params["input_token"]
        output_token: str = params["output_token"]
        input_amount: int = params["input_amount"]
        min_output_amount: int = params["min_output_amount"]
        # AppIntentBase contracts capture output tokens, verify invariants,
        # and forward to the user themselves. Swap output must go to the
        # contract address so _gained() / _snapshot() work correctly.
        recipient: str = state.contract_address or params.get("receiver", state.owner)
        fee_tier: int = params.get("fee_tier", self.default_fee_tier)

        chain_id = context.chain_id
        router_address = self._get_router(chain_id)
        deadline = context.timestamp + self.deadline_offset

        # Build interactions: approve then swap
        interactions = [
            # 1. Approve the router to spend input tokens
            Interaction(
                target=input_token,
                value="0",
                call_data=encode_approve(router_address, input_amount),
                chain_id=chain_id,
            ),
            # 2. Execute the swap via exactInputSingle
            Interaction(
                target=router_address,
                value="0",
                call_data=encode_exact_input_single(
                    token_in=input_token,
                    token_out=output_token,
                    fee=fee_tier,
                    recipient=recipient,
                    deadline=deadline,
                    amount_in=input_amount,
                    amount_out_minimum=0,  # contract enforces order min; tight swap-leg min self-reverts ("Too little received") on tight-margin orders
                    chain_id=chain_id,
                ),
                chain_id=chain_id,
            ),
        ]

        return ExecutionPlan(
            intent_id=intent.app_id,
            interactions=interactions,
            deadline=deadline,
            nonce=state.nonce,
            metadata={
                "route": "uniswap_v3",
                "fee_tier": fee_tier,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": str(input_amount),
                "min_output_amount": str(min_output_amount),
            },
        )

    async def on_score_received(
        self,
        intent: AppIntentDefinition,
        plan: ExecutionPlan,
        score: ScoreResult,
    ) -> None:
        """Log score feedback. The baseline solver does not learn.

        A production solver would use this to tune parameters like
        fee tier selection, slippage tolerance, and routing strategy.
        """
        logger.info(
            "SwapIntentProcessor score received: %.3f (valid=%s) for intent %s",
            score.score,
            score.valid,
            intent.app_id,
        )

    def _extract_swap_params(
        self,
        intent: AppIntentDefinition,
        state: IntentState,
    ) -> dict[str, Any]:
        """Extract and validate swap parameters from intent + state.

        Swap parameters can come from two places:
        1. state.raw_params -- runtime parameters set when the intent is triggered
        2. Intent config -- static defaults

        Args:
            intent: The intent definition.
            state: The on-chain intent state.

        Returns:
            Dictionary with validated swap parameters.

        Raises:
            ValueError: If required parameters are missing.
        """
        if isinstance(state.typed_context, SwapIntentContext):
            return {
                "input_token": state.typed_context.input_token,
                "output_token": state.typed_context.output_token,
                "input_amount": state.typed_context.input_amount,
                "min_output_amount": state.typed_context.min_output_amount,
                "receiver": state.typed_context.receiver,
                "fee_tier": state.typed_context.fee_tier,
            }

        params = _state_params(state)
        normalized = normalize_swap_intent_params(
            params,
            manifest=manifest_from_definition(intent),
            intent_name=_intent_function_from_state(state, "swap"),
            receiver_default=state.contract_address or state.owner,
            slippage_bps=self.slippage_bps,
        )

        input_token = normalized.get("input_token")
        output_token = normalized.get("output_token")
        input_amount = normalized.get("input_amount", 0)

        if not input_token:
            raise ValueError("Missing required parameter: input_token in state.raw_params")
        if not output_token:
            raise ValueError("Missing required parameter: output_token in state.raw_params")
        if input_amount <= 0:
            raise ValueError(f"input_amount must be positive, got {input_amount}")

        result: dict[str, Any] = {
            "input_token": input_token,
            "output_token": output_token,
            "input_amount": input_amount,
            "min_output_amount": normalized["min_output_amount"],
            "receiver": normalized["receiver"],
            "fee_tier": normalized["fee_tier"],
        }

        return result

    def _get_router(self, chain_id: int) -> str:
        """Get the Uniswap V3 router address for a chain.

        Args:
            chain_id: Target chain ID.

        Returns:
            Router contract address.

        Raises:
            ValueError: If no router is known for the chain.
        """
        router = UNISWAP_V3_ROUTERS.get(chain_id)
        if not router:
            raise ValueError(
                f"No Uniswap V3 router configured for chain {chain_id}. "
                f"Supported chains: {list(UNISWAP_V3_ROUTERS.keys())}"
            )
        return router
