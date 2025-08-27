# NeuroRPC Documentation

Welcome to the **NeuroRPC** project documentation.  

**NeuroRPC** is a Python-based framework that provides an interface for **remote procedure calls (RPC)** over **TCP/IP** in the context of distributed and embedded systems.  
The library has been specifically developed to facilitate communication between Python applications and the **LabVIEW Actor Framework**, enabling reproducible, modular, and low-latency control architectures for experimental platforms.

---

## Objectives

The primary objectives of **NeuroRPC** are:

- To offer a **transparent client–server model** for exchanging structured messages between heterogeneous environments (Python ↔ LabVIEW).  
- To enable the design of **actor-based systems** in which commands and data streams are handled as serializable messages.  
- To support **scientific instrumentation workflows**, such as real-time data acquisition, signal analysis, and closed-loop experimental control.  
- To provide a foundation that can be **extended to other protocols or platforms** while preserving consistency and interoperability.

---

## Key Features

- **TCP-based communication layer** ensuring reliable and ordered message delivery.  
- **Serialization/deserialization** mechanisms compatible with LabVIEW binary flattening.  
- **Actor-oriented modularity**, allowing processes to be encapsulated as autonomous units.  
- **Cross-platform support** through Python and LabVIEW integration.  
- **Documentation auto-generation** via [MkDocs](https://www.mkdocs.org/) and [mkdocstrings](https://mkdocstrings.github.io/).

---

## Structure of This Documentation

- **Conceptual Overview** – background on the RPC model, actor-based design principles, and system architecture.  
- **[API Reference](reference/Benchmark.md)** – detailed technical specification of modules, classes, and methods.  
- **Examples and Workflows** – application to data acquisition, remote control, and message handling.  
- **Integration Guidelines** – recommendations for extending NeuroRPC within experimental or industrial frameworks.

---

## Quickstart

Minimal client example

```bash
from neuro_rpc import Client

client = Client("127.0.0.1", port=2001)
client.rpc("Display Text", {"Message": "Trying something :)", "exec_time": 0}, False)

