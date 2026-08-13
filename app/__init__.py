"""MoneyPrinterTurbo 应用包元数据。"""

# 上游 MoneyPrinterTurbo 版本。同步上游时只更新这个值。
__version__ = "1.3.4"

# MoneyPrinterTurbo-NAS 使用独立、连续递增的版本序列。
# 该序号绝不因上游版本升级而重置：
# 例如 1.3.4-nas.2 -> 1.3.5-nas.3 -> 1.4.0-nas.4。
__nas_revision__ = 2
__nas_version__ = f"nas.{__nas_revision__}"

# 完整显示版本同时保留上游基线，方便判断当前 NAS 版本基于哪个官方版本。
__fork_version__ = f"{__version__}-{__nas_version__}"
