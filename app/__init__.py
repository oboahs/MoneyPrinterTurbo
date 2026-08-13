"""MoneyPrinterTurbo 应用包元数据。"""

# 上游 MoneyPrinterTurbo 版本。同步上游时只更新这个值。
__version__ = "1.3.4"

# MoneyPrinterTurbo-NAS 使用独立、连续递增的自定义版本序列。
# 只有本仓库自己的定制功能新增/调整并形成一个新的 NAS 版本时，才递增该序号。
# 如果只是合并上游更新，则 NAS revision 必须保持不变，只更新 __version__。
# 例如：
#   1.3.4-nas.5 --仅同步上游 1.3.5--> 1.3.5-nas.5
#   1.3.5-nas.5 --新增本仓库定制功能--> 1.3.5-nas.6
__nas_revision__ = 2
__nas_version__ = f"nas.{__nas_revision__}"

# 完整显示版本同时保留当前上游基线和 NAS 自定义修订号。
__fork_version__ = f"{__version__}-{__nas_version__}"
