# Debug ML Inference Runbook

## Trigger

Use this when `/predict` returns unexpected scores, 422s, or model errors.

## Procedure

1. Capture request id, payload shape, model version, deployment id, and response envelope.
2. Validate the payload through Pydantic and Pandera to separate schema errors from model errors.
3. Rebuild the same row as a DataFrame and run the feature transformation locally.
4. Compare transformed columns with training manifest feature names.
5. If the model output is plausible but wrong, move to performance or drift review.

## Exit Criteria

The debug session ends with a classified cause: bad input, schema drift, feature drift, model regression, or
infrastructure error.
