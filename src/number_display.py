"""計算精度を維持し、表示する数値だけを小数点以下2桁に切り捨てる。"""

from decimal import Decimal, ROUND_DOWN


def truncate_display(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def format_display(value, *, grouped=False):
    return format(truncate_display(value), ",.2f" if grouped else ".2f")
