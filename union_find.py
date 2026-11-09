class UnionFind:
    """Groups duplicate items together."""

    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x):
        # new item: it is its own group
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        # path compression: point straight to the root
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return  # already in same group
        # union by rank: attach the smaller tree under the bigger one
        if self.rank[root_a] < self.rank[root_b]:
            self.parent[root_a] = root_b
        elif self.rank[root_a] > self.rank[root_b]:
            self.parent[root_b] = root_a
        else:
            self.parent[root_b] = root_a
            self.rank[root_a] += 1

    def connected(self, a, b):
        return self.find(a) == self.find(b)

    def groups(self):
        result = {}
        for item in list(self.parent):
            result.setdefault(self.find(item), []).append(item)
        return result


if __name__ == "__main__":
    uf = UnionFind()
    uf.union(1, 2)
    uf.union(2, 3)
    uf.union(4, 5)

    assert uf.connected(1, 3)
    assert not uf.connected(1, 4)
    assert len(uf.groups()) == 2
    print("Groups:", list(uf.groups().values()))
    print("All tests passed!")
    