from python.labview_data import serialize_variant, deserialize_variant
import numpy as np

if __name__ == '__main__':
    """params = {"Message": "Testing", "Numeric": 1996, "Boolean": False}

    print(msgpack.packb(params).hex())

    headers = "83A5 4163 746F 72AB 4368 6174 2057 696E 646F 77A7 4D65 7373 6167 65AA 6563 686F 2072 6570 6C79 A850 7269 6F72 6974 7901"
    headers = msgpack.unpackb(bytes.fromhex(headers))

    data = "83A7 4D65 7373 6167 65A6 4167 656E 7465 A269 64A3 3030 37A9 6578 6563 5F74 696D 65CB 409F 3000 0000 0000"
    data = msgpack.unpackb(bytes.fromhex(data))

    print(headers)
    print(data)

    # Deserialize Headers and Data
    test = "82A7 4865 6164 6572 73C4 3083 A541 6374 6F72 AB43 6861 7420 5769 6E64 6F77 A74D 6573 7361 6765 AA65 6368 6F20 7265 706C 79A8 5072 696F 7269 7479 01A4 4461 7461 C42A 83A7 4D65 7373 6167 65A6 4167 656E 7465 A269 64A3 3030 37A9 6578 6563 5F74 696D 65CB 409F 3000 0000 0000"
    test = msgpack.unpackb(bytes.fromhex(test))
    print(f"Headers and Data: {test}")

    # Deserialize Headers and Data content
    test.update({"Headers": msgpack.unpackb((test["Headers"]))})
    test.update({"Data": msgpack.unpackb((test["Data"]))})
    print(f"Headers and Data content deserialized: {test}")

    # Update data
    test["Data"]["Message"] = "Hello World!"
    test["Headers"]["Actor"] = "Rasputia"
    print(f"Info updated: {test}")

    # Serialize Headers and Data content
    test.update({"Headers": msgpack.packb(test["Headers"])})
    test.update({"Data": msgpack.packb(test["Data"])})
    print(f"Headers and Data serialized: {test}")

    # Serialize Headers and Data
    print(msgpack.packb(test).hex())

    test = "82A7 4865 6164 6572 73C4 3383 A541 6374 6F72 AB43 6861 7420 5769 6E64 6F77 A74D 6573 7361 6765 AD55 7064 6174 6520 4E75 6D62 6572 A850 7269 6F72 6974 7901 A444 6174 61C4 01C0"
    test = msgpack.unpackb(bytes.fromhex(test))
    print(test)

    # Deserialize Headers and Data content
    test.update({"Headers": msgpack.unpackb((test["Headers"]))})
    test.update({"Data": msgpack.unpackb((test["Data"]))})
    print(f"Headers and Data content deserialized: {test}")


    new = "82D9 0748 6561 6465 7273 DC00 39CC 83CC D9CC 05CC 41CC 63CC 74CC 6FCC 72CC D9CC 0BCC 43CC 68CC 61CC 74CC 20CC 57CC 69CC 6ECC 64CC 6FCC 77CC D9CC 07CC 4DCC 65CC 73CC 73CC 61CC 67CC 65CC D9CC 0ACC 65CC 63CC 68CC 6FCC 20CC 72CC 65CC 70CC 6CCC 79CC D9CC 08CC 50CC 72CC 69CC 6FCC 72CC 69CC 74CC 79CC D2CC 00CC 00CC 00CC 01D9 0444 6174 61DC 004A CC83 CCD9 CC07 CC4D CC65 CC73 CC73 CC61 CC67 CC65 CCD9 CC00 CCD9 CC02 CC69 CC64 CCD9 CC24 CC62 CC31 CC35 CC36 CC30 CC35 CC36 CC36 CC2D CC38 CC65 CC61 CC35 CC2D CC34 CC64 CC32 CC62 CC2D CC61 CC64 CC62 CC30 CC2D CC65 CC33 CC63 CC62 CC64 CC65 CC36 CC36 CC30 CC32 CC39 CC38 CCD9 CC09 CC65 CC78 CC65 CC63 CC5F CC74 CC69 CC6D CC65 CCCB CC00 CC00 CC00 CC00 CC00 CC00 CC00 CC00"
    new = bytes.fromhex(new)
    new = msgpack.unpackb(new)

    print(new)
    """

    test = ("James", np.int32(7), "Bond")
    print(test)

    tests = serialize_variant(test)
    print(tests.hex())

    tests = "1800 8000 0000 0004 000E 4030 FFFF FFFF 044E 616D 6500 000D 4003 0006 4E75 6D62 6572 0000 1240 30FF FFFF FF08 4C61 7374 6E61 6D65 0000 0C00 5000 0300 0000 0100 0200 0100 0300 0000 054A 616D 6573 0000 0007 0000 0004 426F 6E64 0000 0000 "
    tests = bytes.fromhex(tests)
    print(tests)
    test = deserialize_variant(tests)
    print(test)

    from python.labview_data.type_converters import ClusterConverter
    from python.labview_data.utils import SerializationData

    # Paso 1: Define el cluster (como tupla)
    cluster_value = ("Joseph", 2000, "LaCroix")

    # Paso 2: Serializa manualmente cada elemento
    info = SerializationData(version=0)  # puedes usar también 0x18008000 si prefieres
    serialized_cluster = ClusterConverter.serialize(cluster_value, info)

    # Paso 3: Accede al buffer plano (sin encabezado de variant)
    raw_bytes = serialized_cluster.flat_buffer()
    print(cluster_value)
    print("Hex:", raw_bytes.hex()) # 000000064a6f7365706800000000000007d0000000074c6143726f6978

    from python.labview_data.utils import num2bytes, str2bytes

    name = str2bytes("Joseph")  # u4-length-prefixed string
    number = num2bytes(2000, dtype=">i4")
    lastname = str2bytes("LaCroix")

    raw = name + number + lastname
    print(raw.hex()) #000000064a6f73657068000007d0000000074c6143726f6978

    from python.labview_data.types import Cluster
    cluster = Cluster(["James", np.int32(2000), "Bond"], names=["name", "number", "lastname"])
    d = cluster.__dict__()
    print(d)
    info = SerializationData(version=0)  # puedes usar también 0x18008000 si prefieres
    serialized_cluster = ClusterConverter.serialize(cluster, info)

    # Paso 3: Accede al buffer plano (sin encabezado de variant)
    raw_bytes = serialized_cluster.flat_buffer()
    print("Hex:", raw_bytes.hex())


