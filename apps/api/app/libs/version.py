class Version:
    def __init__(self, version: str | int):
        if isinstance(version, str):
            self._init_from_str(version)
        elif isinstance(version, int):
            self._init_from_num(version)
        else:
            raise ValueError("version must be a string or an integer")

    def increment(self, count: int = 1):
        self.version_num += count
        self._init_from_num(self.version_num)
        return self

    def _init_from_str(self, version_str: str):
        parts = version_str.split(".")
        if len(parts) > 3:
            raise ValueError("version string must not have more than three parts")
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            raise ValueError("version string must be an integer")

        parts += [0] * (3 - len(parts))
        x, y, z = parts
        if not (0 <= x <= 999 and 0 <= y <= 999 and 0 <= z <= 999):
            raise ValueError("each part must be between 0 and 999")

        self.version_num = x * 1000000 + y * 1000 + z
        self.version_str = self._format_version_str(x, y, z)

    def _init_from_num(self, version_num: int):
        if not isinstance(version_num, int):
            raise TypeError("version_num must be an integer")
        if version_num < 0 or version_num > 999999999:
            raise ValueError("version_num must be between 0 and 999999999")

        x = version_num // 1000000
        remaining = version_num % 1000000
        y = remaining // 1000
        z = remaining % 1000

        self.version_num = version_num
        self.version_str = self._format_version_str(x, y, z)

    def _format_version_str(self, x: int, y: int, z: int) -> str:
        return f"{x}.{y}.{z}"

    def __str__(self):
        return self.version_str

    def __int__(self):
        return self.version_num

    def __repr__(self):
        return (
            f"Version(version_str='{self.version_str}', version_num={self.version_num})"
        )

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.version_num == other.version_num

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.version_num < other.version_num

    def __hash__(self):
        return hash(self.version_num)
