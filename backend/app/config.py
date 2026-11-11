"""全局配置：所有时间统一按北京时间（UTC+8）的 naive datetime 处理。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "billing.duckdb"

# 相邻有效读数允许的最大间隔（秒）：超过即判定为缺测区间
MAX_GAP_SECONDS = 30 * 60

# 费用中间计算保留的展示位数（最终在账单总额处舍入到分）
MONEY_DISPLAY_DP = 6
MONEY_FINAL_DP = 2  # 账单总额最终舍入到分

# 电量分配展示精度（kWh），内部始终使用完整 Decimal 精度
ENERGY_DISPLAY_DP = 6
