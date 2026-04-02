"""
Recursive descent parser for alpha factor expressions.

Converts expression strings like "cs_rank(ts_corr(close, volume, 10))"
into an AST of typed nodes. Validates function names, column names,
and window parameter bounds at parse time.

Grammar:
    expr      → term (('+' | '-') term)*
    term      → unary (('*' | '/') unary)*
    unary     → '-' unary | atom
    atom      → NUMBER | func_call | column_ref | '(' expr ')'
    func_call → IDENT '(' expr (',' expr)* ')'
    column_ref→ IDENT  (if IDENT in VALID_COLUMNS)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from strategy.signals.expression.operators import OPERATOR_REGISTRY, VALID_COLUMNS


# ── AST nodes ─────────────────────────────────────────────────────────────────


@dataclass
class NumberNode:
    value: float


@dataclass
class ColumnNode:
    name: str  # one of VALID_COLUMNS


@dataclass
class FuncCallNode:
    name: str
    args: list  # list of AST nodes


@dataclass
class BinOpNode:
    op: str  # '+', '-', '*', '/'
    left: object
    right: object


@dataclass
class UnaryNegNode:
    child: object


# Union type for type hints
Node = NumberNode | ColumnNode | FuncCallNode | BinOpNode | UnaryNegNode


# ── Tokenizer ─────────────────────────────────────────────────────────────────

TOKEN_RE = re.compile(
    r"""
    (?P<NUMBER>  \d+(?:\.\d+)?  )  |
    (?P<IDENT>   [a-zA-Z_]\w*   )  |
    (?P<LPAREN>  \(              )  |
    (?P<RPAREN>  \)              )  |
    (?P<COMMA>   ,               )  |
    (?P<OP>      [+\-*/]        )  |
    (?P<WS>      \s+            )
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    type: str   # NUMBER, IDENT, LPAREN, RPAREN, COMMA, OP
    value: str


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if m is None:
            raise ParseError(f"Unexpected character at position {pos}: {text[pos]!r}")
        pos = m.end()
        if m.lastgroup == "WS":
            continue
        tokens.append(Token(type=m.lastgroup, value=m.group()))
    return tokens


# ── Parser ────────────────────────────────────────────────────────────────────


class ParseError(Exception):
    """Raised when an expression cannot be parsed."""


class Parser:
    """Recursive descent parser producing an AST from a token list."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, token_type: str) -> Token:
        tok = self._peek()
        if tok is None or tok.type != token_type:
            found = tok.value if tok else "EOF"
            raise ParseError(f"Expected {token_type}, got {found!r}")
        return self._advance()

    # ── Grammar rules ─────────────────────────────────────────────────────

    def parse(self) -> Node:
        node = self._expr()
        if self.pos < len(self.tokens):
            raise ParseError(
                f"Unexpected token after expression: {self.tokens[self.pos].value!r}"
            )
        return node

    def _expr(self) -> Node:
        """expr → term (('+' | '-') term)*"""
        left = self._term()
        while (tok := self._peek()) and tok.type == "OP" and tok.value in "+-":
            op = self._advance().value
            right = self._term()
            left = BinOpNode(op=op, left=left, right=right)
        return left

    def _term(self) -> Node:
        """term → unary (('*' | '/') unary)*"""
        left = self._unary()
        while (tok := self._peek()) and tok.type == "OP" and tok.value in "*/":
            op = self._advance().value
            right = self._unary()
            left = BinOpNode(op=op, left=left, right=right)
        return left

    def _unary(self) -> Node:
        """unary → '-' unary | atom"""
        tok = self._peek()
        if tok and tok.type == "OP" and tok.value == "-":
            self._advance()
            child = self._unary()
            return UnaryNegNode(child=child)
        return self._atom()

    def _atom(self) -> Node:
        """atom → NUMBER | func_call | column_ref | '(' expr ')'"""
        tok = self._peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")

        # Number literal
        if tok.type == "NUMBER":
            self._advance()
            return NumberNode(value=float(tok.value))

        # Identifier — function call or column reference
        if tok.type == "IDENT":
            name = tok.value
            self._advance()
            # Check if followed by '(' → function call
            if (nxt := self._peek()) and nxt.type == "LPAREN":
                return self._func_call(name)
            # Otherwise, column reference
            if name not in VALID_COLUMNS:
                raise ParseError(
                    f"Unknown column: {name!r}. Valid: {sorted(VALID_COLUMNS)}"
                )
            return ColumnNode(name=name)

        # Parenthesised sub-expression
        if tok.type == "LPAREN":
            self._advance()
            node = self._expr()
            self._expect("RPAREN")
            return node

        raise ParseError(f"Unexpected token: {tok.value!r}")

    def _func_call(self, name: str) -> FuncCallNode:
        """func_call → IDENT '(' expr (',' expr)* ')'"""
        if name not in OPERATOR_REGISTRY:
            raise ParseError(
                f"Unknown function: {name!r}. "
                f"Available: {sorted(OPERATOR_REGISTRY)}"
            )
        self._expect("LPAREN")
        args: list[Node] = [self._expr()]
        while (tok := self._peek()) and tok.type == "COMMA":
            self._advance()
            args.append(self._expr())
        self._expect("RPAREN")

        # Validate argument count and window bounds
        spec = OPERATOR_REGISTRY[name]
        expected = spec.n_expr_args + (1 if spec.has_window else 0)
        if len(args) != expected:
            raise ParseError(
                f"{name}() expects {expected} args, got {len(args)}"
            )
        if spec.has_window:
            window_arg = args[-1]
            if not isinstance(window_arg, NumberNode):
                raise ParseError(
                    f"{name}() window parameter must be a number literal"
                )
            d = int(window_arg.value)
            if d < 1 or d > 252:
                raise ParseError(
                    f"{name}() window must be 1–252, got {d}"
                )

        return FuncCallNode(name=name, args=args)


# ── Public API ────────────────────────────────────────────────────────────────


def parse(expression: str) -> Node:
    """Parse an expression string into an AST.

    Raises ParseError on invalid syntax, unknown functions, or bad window sizes.
    """
    tokens = tokenize(expression)
    if not tokens:
        raise ParseError("Empty expression")
    return Parser(tokens).parse()
