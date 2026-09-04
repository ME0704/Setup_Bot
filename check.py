import bias_engine, pattern, sweep_rule, structure, liquidity, alert, timeutil

checks = [
    ("bias_engine.evaluate_pair", hasattr(bias_engine, "evaluate_pair")),
    ("pattern.detect_shape_rejection", hasattr(pattern, "detect_shape_rejection")),
    ("sweep_rule.detect_sweep_rejection", hasattr(sweep_rule, "detect_sweep_rejection")),
    ("structure.determine_trend", hasattr(structure, "determine_trend")),
    ("structure.detect_bos", hasattr(structure, "detect_bos")),
    ("liquidity.detect_sweep", hasattr(liquidity, "detect_sweep")),
    ("alert.format_message", hasattr(alert, "format_message")),
    ("timeutil.format_eat_compact", hasattr(timeutil, "format_eat_compact")),
    ("timeutil.format_eat_sent", hasattr(timeutil, "format_eat_sent")),
]

for name, ok in checks:
    print(f"{name}: {ok}")