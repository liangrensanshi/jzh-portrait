"""跨页面公用工具"""
import re


def norm_counname(name: str) -> str:
    """把含「医药高新」的长县名统一缩短为「医药高新区（高港区）」"""
    if not name:
        return name
    if "医药高新" in name:
        return "医药高新区（高港区）"
    return name


def period_display(months: list) -> str:
    if not months:
        return "（未选择区间）"
    sy, sm = months[0]
    ey, em = months[-1]
    if (sy, sm) == (ey, em):
        return f"{sy}年{sm}月"
    return f"{sy}年{sm}月—{ey}年{em}月"
