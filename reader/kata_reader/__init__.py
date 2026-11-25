"""kata_reader: sandboxed document extract (PDF and image in, page text and PNG pages out).

The package never touches the network, the database or the core. extract() is pure apart from
writing PNG page files into the out dir it is given; run_extract_isolated() runs it in a child
process with memory, CPU and wall-clock limits.
"""

from kata_reader.extract import Page, Result, extract
from kata_reader.limits import Limits
from kata_reader.sandbox import run_extract_isolated, run_isolated

__all__ = ["Limits", "Page", "Result", "extract", "run_extract_isolated", "run_isolated"]
