from .tools import BinParser


class SKNFile:
    def __init__(self, file):
        if isinstance(file, str):
            file = open(file, "rb")
        if file.read(4) != b"\x33\x22\x11\x00":
            raise ValueError("missing magic code")

        f = BinParser(file)

        self.major, self.minor, self.count = f.unpack("<HHI")
        self.entries = [self.read_object(f) for i in range(self.count)]

        if self.major == 4:
            self.unknown, = f.unpack("<I")

        self.index_count, self.vertex_count = f.unpack("<II")

        if self.major == 4:
            self.vertex_size, = f.unpack("<I")
            self.contains_tangent = bool(f.unpack("<I")[0])
            self.bounding_box_min = f.unpack("<fff")
            self.bounding_box_max = f.unpack("<fff")
            self.bounding_sphere_location = f.unpack("<fff")
            self.bounding_sphere_radius, = f.unpack("<f")

        self.indecies = [f.unpack("<H")[0] for i in range(self.index_count)]
        self.vertices = [self.read_vertex(f) for i in range(self.vertex_count)]

        for entry in self.entries:
            entry["vertices"] = self.vertices[entry["start_vertex"] : entry["start_vertex"] + entry["vertex_count"]]
            entry["indecies"] = self.indecies[entry["start_index"] : entry["start_index"] + entry["index_count"]]
            entry["indecies"] = [x - (0 if x > entry["start_vertex"] else entry["start_vertex"]) for x in entry["indecies"]]

    def read_object(self, f):
        return {
            "name": f.unpack("64s")[0].split(b"\0", 1)[0].decode("utf-8"),
            "start_vertex": f.unpack("<I")[0],
            "vertex_count": f.unpack("<I")[0],
            "start_index": f.unpack("<I")[0],
            "index_count": f.unpack("<I")[0],
        }

    def read_vertex(self, f):
        return {
            "position": f.unpack("<fff"),
            "bone_indecies": f.unpack("<BBBB"),
            "weight": f.unpack("<ffff"),
            "normal": f.unpack("<fff"),
            "uv": f.unpack("<ff"),
            "tangent": f.unpack("<BBBB") if hasattr(self, "contains_tangent") and self.contains_tangent else None,
        }

    def to_obj(self, entry) -> str:
        content = ""
        for vert in entry["vertices"]:
            content += "v %s %s %s\n" % vert["position"]
            content += "vt %s %s\n" % vert["uv"]
            content += "vn %s %s %s\n" % vert["normal"]

        i = 0
        while i < entry["index_count"]:
            a = entry["indecies"][i] + 1
            b = entry["indecies"][i + 1] + 1
            c = entry["indecies"][i + 2] + 1
            content += "f {0}/{0}/{0} {1}/{1}/{1}/ {2}/{2}/{2}\n".format(a, b, c)
            i += 3

        return content
