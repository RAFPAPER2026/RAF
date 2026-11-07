"""人工打分页启动入口（端口 5002）。

`uv run python manual_scorer/main.py --result-dir results --tasks-dir tasks --port 5002`
"""

from manual_scorer.server import main

if __name__ == "__main__":
    main()
