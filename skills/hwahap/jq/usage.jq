# Aggregate codex exec turn.completed usage into one priced unit receipt.
[.[] | select(.type == "turn.completed") | .usage] as $turns
| if ($turns | length) == 0 then error("turn.completed usage is missing") else . end
| ($turns | map(.input_tokens // 0) | add) as $input
| ($turns | map(.cached_input_tokens // 0) | add) as $cached
| ($turns | map(.output_tokens // 0) | add) as $output
| ($turns | map(.reasoning_output_tokens // 0) | add) as $reasoning
| $prices[0].models[$model] as $rate
| if $rate == null then error("model price is missing") else . end
| {
    unit: $unit,
    attempt: ($attempt | tonumber),
    model: $model,
    effort: $effort,
    input_tokens: $input,
    cached_input_tokens: $cached,
    output_tokens: $output,
    reasoning_output_tokens: $reasoning,
    cache_hit_ratio: (if $input == 0 then 0 else $cached / $input end),
    reasoning_ratio: (if $output == 0 then 0 else $reasoning / $output end),
    cost_usd: (((($input - $cached) * $rate.input) + ($cached * $rate.cached_input) + ($output * $rate.output)) / 1000000),
    started: $started,
    ended: $ended,
    seconds: ($seconds | tonumber)
  }
