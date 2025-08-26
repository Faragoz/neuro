"""
Conversion utilities between Python dictionaries/tuples and LabVIEW Clusters.

Provides serialization and deserialization helpers to encode/decode nested
data structures into LabVIEW's Cluster representation. Also integrates with
RPCRequest/RPCResponse to support actor-style communication with LabVIEW classes.

Notes:
    - Extends ClusterConverter from ``python.labview_data.type_converters``.
"""

from python.labview_data.types import Cluster
from python.labview_data.utils import SerializationData, HeaderInfo, DeserializationData
from python.labview_data.type_converters import ClusterConverter

import numpy as np
import json

from python.neuro_rpc.RPCMessage import RPCRequest, RPCResponse


class NpEncoder(json.JSONEncoder):
    """
    JSON encoder for NumPy data types.

    Converts ``numpy.integer``, ``numpy.floating``, and ``numpy.ndarray`` into standard
    Python ``int``, ``float``, and ``list`` for JSON serialization compatibility.
    """
    def default(self, obj):
        """
        Override JSON encoding for NumPy objects.

        Args:
            obj (Any): Object to encode.

        Returns:
            Any: Encoded Python-native type.
        """
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class Proxy(ClusterConverter):
    """
    Proxy class to convert between Python dicts and LabVIEW Cluster bytes.

    Implements bidirectional mapping of nested dict/tuple structures to LabVIEW
    Cluster format, supporting serialization for sending RPC requests and
    deserialization of responses.
    """
    Actor = {"Class name": "", "Priority": np.int32(2), "Data": {}}

    def dict_to_tuple(self, d: dict) -> tuple[list, list]:
        """
        Convert a dictionary into a (values, keys) tuple.

        Recursively descends into nested dictionaries to preserve structure.

        Args:
            d (dict): Input dictionary.

        Returns:
            tuple[list, list]: (values, keys) representation of the dictionary.
        """
        keys = list(d.keys())
        values = []
        for k in keys:
            v = d[k]
            if isinstance(v, dict):
                v = self.dict_to_tuple(v)
            values.append(v)
        return values, keys

    def tuple_to_dict(self, values_keys) -> dict:
        """
        Convert a (values, keys) tuple back into a dictionary.

        Recursively reconstructs nested dictionaries from tuple representations.

        Args:
            values_keys (tuple[list, list]): (values, keys) pair.

        Returns:
            dict: Reconstructed dictionary.
        """
        values, keys = values_keys
        result = {}
        for key, val in zip(keys, values):
            if (
                isinstance(val, tuple)
                and len(val) == 2
                and isinstance(val[0], list)
                and isinstance(val[1], list)
            ):
                result[key] = self.tuple_to_dict(val)
            else:
                result[key] = val
        return result

    def to_cluster_bytes_with_tree(
        self,
        tup: tuple[list, list],
        sdata: SerializationData = None,
        encoding: str = "ansi"
    ) -> tuple[bytes, dict]:
        """
        Serialize a (values, keys) tuple into a LabVIEW Cluster flat buffer.

        Args:
            tup (tuple[list, list]): (values, keys) representation of the cluster.
            sdata (SerializationData, optional): Serialization metadata. Defaults to version=0.
            encoding (str): Encoding to use for nested buffers. Defaults to "ansi".

        Returns:
            tuple[bytes, dict]: (flat buffer, metadata tree).
        """
        if sdata is None:
            sdata = SerializationData(version=0)

        values, keys = tup
        processed = []
        children = []

        for idx, v in enumerate(values):
            if isinstance(v, tuple):
                buf_str, subtree = self.to_cluster_bytes_with_tree(v, sdata, encoding)
                processed.append(buf_str.decode(encoding))
                children.append({
                    "index": idx,
                    "keys": v[1],
                    "tree": subtree
                })
            else:
                processed.append(v)

        cluster = Cluster(processed, keys)
        res = ClusterConverter.serialize(cluster, sdata)

        return (
            res.flat_buffer(),
            {
                "header": res.flat_header(),
                "keys": keys,
                "children": children
            }
        )

    def from_cluster_bytes_and_tree(
        self,
        raw_bytes: bytes,
        hdr_tree: dict,
        sdata: SerializationData = None,
        encoding: str = "ansi"
    ) -> tuple[list, list]:
        """
        Reconstruct a (values, keys) tuple from Cluster bytes and metadata tree.

        Args:
            raw_bytes (bytes): Flat buffer for the cluster.
            hdr_tree (dict): Metadata tree including headers, keys, and children.
            sdata (SerializationData, optional): Deserialization context.
            encoding (str): Encoding used for string payloads. Defaults to "ansi".

        Returns:
            tuple[list, list]: (values, keys) structure.
        """
        if sdata is None:
            sdata = SerializationData(version=0)

        full = hdr_tree["header"] + raw_bytes
        hi = HeaderInfo.parse(full, offset_h=0)
        dd = DeserializationData(
            header=hi,
            buffer=full,
            offset_d=hi.end,
            version=sdata.version
        )

        vals = list(ClusterConverter.deserialize(dd).value)
        keys = hdr_tree["keys"]

        for child in hdr_tree.get("children", []):
            idx = child["index"]
            sub_tree = child["tree"]
            buf_sub = vals[idx].encode(encoding)
            vals[idx] = self.from_cluster_bytes_and_tree(buf_sub, sub_tree, sdata, encoding)

        return vals, keys

    def to_act(self, Message):
        """
        Convert an RPCRequest/Message dict into a LabVIEW Actor Cluster.

        Args:
            Message (dict | RPCRequest): Message to encode.

        Returns:
            tuple[bytes, dict]: (flat buffer, metadata tree).
        """
        if isinstance(Message, RPCRequest):
            Message = Message.to_dict()

        id = Message.pop("id")
        Message["params"] = {"id": id, **Message["params"]}

        self.Actor["Class name"] = f"Chat Window.lvlib:{Message['method']} Msg.lvclass"
        self.Actor["Data"] = {
            "Message": Message["params"]["Message"],
            "id": Message["params"]["id"],
            "exec_time": np.int32(0)
        }
        tupla = self.dict_to_tuple(self.Actor)

        self.to_cluster_bytes_with_tree(tupla)
        return self.to_cluster_bytes_with_tree(tupla)

    def from_act(self, raw_bytes: bytes, hdr_tree: dict):
        """
        Convert LabVIEW Actor Cluster bytes back into an RPCResponse.

        Args:
            raw_bytes (bytes): Cluster flat buffer.
            hdr_tree (dict): Metadata tree from serialization.

        Returns:
            dict: RPCResponse serialized as dictionary.
        """
        recovered_vals, recovered_keys = self.from_cluster_bytes_and_tree(raw_bytes, hdr_tree)
        dict_ = self.tuple_to_dict((recovered_vals, recovered_keys))
        id = dict_["Data"].pop("id")

        return RPCResponse(id=id, result=dict_["Data"]).to_dict()


if __name__ == '__main__':
    # Example usage for debugging
    id = "6b371397-9fbe-4d90-9283-6aec836abe68"
    RPC = RPCRequest(method='echo reply', id=id, params={"Message": "", "exec_time": 0}).to_dict()

    proxy = Proxy()
    raw_buf, hdr_tree = proxy.to_act(RPC)

    response = proxy.from_act(raw_buf, hdr_tree)

    raw_buf = "0000 0028 4368 6174 2057 696E 646F 772E 6C76 6C69 623A 6563 686F 2072 6570 6C79 204D 7367 2E6C 7663 6C61 7373 0000 0001 0000 0034 0000 0000 0000 0024 3662 3337 3133 3937 2D39 6662 652D 3464 3930 2D39 3238 332D 3661 6563 3833 3661 6265 3939 0000 0000 0000 0000 "
    raw_buf = bytes.fromhex(raw_buf)
    response = proxy.from_act(raw_buf, hdr_tree)
    print(response)
