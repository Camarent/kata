"""Reader: the core side of the sandboxed document reader (M23).

Core stores the uploaded document, queues `reader.extract` and checks the worker's reply. It never
imports `kata_reader`: the extract runs in the reader container, behind the spool protocol.
"""
