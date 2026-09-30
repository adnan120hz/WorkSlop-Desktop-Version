import ast
import operator as _op
import xml.etree.ElementTree as tree

tree.register_namespace('', "http://www.apple.com/CoreAnimation/1.0")

# B8-family fix: the old parse_equation ran eval() on the template's
# "nuggetOffset" attribute with __builtins__ stripped. That does NOT make
# eval safe — attribute access needs no builtins, so a malicious template
# could escape the sandbox (e.g. ().__class__.__base__.__subclasses__()).
# Templates only need plain arithmetic over x/y/z/a, so evaluate with a
# tiny AST walker that permits nothing else.
_ALLOWED_BINOPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
    ast.Div: _op.truediv, ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod, ast.Pow: _op.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: _op.pos, ast.USub: _op.neg}


def _safe_eval_arith(expr: str, names: dict) -> float:
    def _walk(node):
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise ValueError(f"bad constant {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise ValueError(f"unknown name {node.id!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            return _ALLOWED_BINOPS[type(node.op)](_walk(node.left), _walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
            return _ALLOWED_UNARYOPS[type(node.op)](_walk(node.operand))
        raise ValueError(f"forbidden expression {ast.dump(node)!r}")

    try:
        parsed = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"bad equation {expr!r}: {e}")
    return _walk(parsed)


def parse_equation(eq: str, val: str):
    eqns = eq.split(',')
    value = [val]
    if ' ' in val:
        # convert to array
        value = val.split(' ')
    # map the value to floats
    value = list(map(lambda x: float(x), value))
    keys = ['x', 'y', 'z', 'a']
    results = []
    mapped = dict(zip(keys, value))
    for eqn in eqns:
        results.append(str(_safe_eval_arith(eqn.strip(), mapped)))
    # map back to string
    return ' '.join(results)

def set_xml_value(file: str, id: str, key: str, val: any, use_ca_id: bool = False):
    set_xml_values(file=file, id=id, keys=[key], values=[val], use_ca_id=use_ca_id)

def set_xml_values(file: str, id: str, keys: list[str], values: list[any], use_ca_id: bool = False):
    xml = tree.parse(file)
    root = xml.getroot()

    # convert bool to integer
    for i in range(len(values)):
        if isinstance(values[i], bool):
            values[i] = int(values[i])
        # convert value to string
        if not isinstance(values[i], str):
            values[i] = str(values[i])

    # set all values with the nugget id passed by param
    if use_ca_id:
        idKey = "id"
    else:
        idKey = "nuggetId"
    for to_change in root.findall(f".//*[@{idKey}='{id}']"):
        eqn = to_change.get("nuggetOffset")
        # TODO: Allow offsets for more than just the first value
        for i in range(len(keys)):
            offsetVal = values[i]
            if i == 0 and eqn != None:
                offsetVal = parse_equation(eqn, offsetVal)
            to_change.set(keys[i], offsetVal)
    if use_ca_id:
        # also look for target id
        for to_change in root.findall(f".//*[@targetId='{id}']"):
            for i in range(len(keys)):
                # find the value type
                set_val = values[i]
                to_change.set(keys[i], set_val)

    # write back to file
    xml.write(file, encoding="UTF-8", xml_declaration=True)

def remove_from_root(root, search):
    for parent in root.findall(search + "/.."):
        for prop in parent.findall(search):
            parent.remove(prop)

def delete_xml_value(file: str, id: str, use_ca_id: bool = False):
    xml = tree.parse(file)
    root = xml.getroot()

    # delete all elements with the nugget id passed by param
    if use_ca_id:
        idKey = "id"
    else:
        idKey = "nuggetId"
    remove_from_root(root, search=f".//*[@{idKey}='{id}']")
    if use_ca_id:
        # also remove the target ids
        remove_from_root(root, search=f".//*[@targetId='{id}']")
    
    # write back to file
    xml.write(file, encoding="UTF-8", xml_declaration=True)