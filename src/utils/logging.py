"""日志配置模块."""

import logging
import sys
import time
from pathlib import Path


class BeijingFormatter(logging.Formatter):
    """北京时间格式化器."""
    
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
            s = "%s,%03d" % (t, record.msecs)
        return s


def beijing_time_converter(secs: float | None = None) -> time.struct_time:
    """将时间戳转换为北京时间."""
    if secs is None:
        secs = time.time()
    return time.localtime(secs + 8 * 3600)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """配置全局日志.

    Parameters
    ----------
    level : str
        日志级别
    log_file : str | Path | None
        日志文件路径, None 则只输出到控制台
    fmt : str
        日志格式
    """
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    # 使用北京时间格式化器
    formatter = BeijingFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    formatter.converter = beijing_time_converter
    
    for handler in handlers:
        handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )
