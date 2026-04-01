import ast

class NormalizeNames(ast.NodeTransformer):
    def __init__(self):
        self.mapping = {}
        self.counter = 0

    def visit_Name(self, node):
        if node.id not in self.mapping:
            self.mapping[node.id] = f"var{self.counter}"
            self.counter += 1
        node.id = self.mapping[node.id]
        return node


def get_ast_tree(code):
    try:
        tree = ast.parse(code)
        tree = NormalizeNames().visit(tree)
        return tree, None
    except Exception as e:
        return None, str(e)


def pretty_ast(tree, indent=0):
    result = ""
    for node in ast.iter_child_nodes(tree):
        result += "  " * indent + type(node).__name__ + "\n"
        result += pretty_ast(node, indent + 1)
    return result