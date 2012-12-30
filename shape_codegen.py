from traversal import Traversal 

from array_type import ArrayT, SliceT
from closure_type import ClosureT
from core_types import ScalarT, NoneT 
from syntax import Const 
from tuple_type import TupleT 


from shape import unknown_scalar, const, Scalar 
from shape import Var, Closure 

class ArgConverter(Traversal):
  def __init__(self, codegen):
    self.codegen = codegen 
    self.var_counter = 0
    self.env = {}
  
  def fresh_var(self):
    n = self.var_counter 
    self.var_counter += 1
    return Var(n) 
  
  def bind(self, scalar_value):
    v = self.fresh_var()
    self.env[v] = scalar_value 
  
   
  def convert(self, x):
    t = x.type
    if isinstance(t, ScalarT):
      self.bind(x)     
    elif isinstance(t, ArrayT):
      shape = self.codegen.shape(x)
      shape_elts = self.codegen.tuple_elts(shape)
      return self.convert_list(shape_elts)
    elif isinstance(t, TupleT):
      elts = self.codegen.tuple_elts(x)
      self.convert_list(elts)
    elif isinstance(t, ClosureT):
      return Closure(t.fn, self.convert_list(t.arg_types))
    else:
      assert False, "[shape_codegen] Not supported %s : %s" % (x,x.type)

  def convert_list(self, xs):
    for x in xs:
      self.convert(x)

import syntax_helpers 

class ShapeCodegen(Traversal):
  
  def __init__(self, codegen, exprs):
    self.codegen = codegen
    conv = ArgConverter(codegen)
    self.exprs = exprs 
    conv.convert_list(exprs)
    self.env = conv.env 
    
  def visit_Var(self, v):
    return self.env[v]  
  
  def visit_Const(self, v):
    return syntax_helpers.const(v.value) 
    
  def visit_Shape(self, v):
    return self.codegen.tuple([self.visit(d) for d in v.dims])
    
  def visit_Dim(self, v):
    return self.codegen.tuple_proj(self.visit(v.array), v.dim)
  
  def visit_UnknownScalar(self, v):
    assert False, "Can't generate shape expression for unknown scalar"
    
  def visit_Tuple(self, v):
    return self.codegen.tuple(self.visit(e) for e in v.elts)
    
  def binop(self, op_name, v):
    x = self.visit(v.x)
    y = self.visit(v.y)
    op = getattr(self.codegen, op_name)
    return op(x,y)
   
  def visit_Sub(self, v):
    return self.binop('sub', v)
    
  def visit_Add(self, v):
    return self.binop('add', v)
    
  def visit_Mult(self, v):
    return self.binop('mult', v)
      
    
  def visit_Div(self, v):
    return self.binop('div', v)
   
  def visit_Mod(self, v):
    return self.binop('mod', v)
  
  def visit_Closure(self, v):
    assert False, "Unexpected closure in result shape: %s" % (v,)
    
def make_shape_expr(codegen, symbolic_shape, input_exprs):
  """
  Given a codegen object we're currently using to create a 
  function, and a symbolic result shape of a function call 
  (along with the input expressions that went into the function)
  generate a code expression for the shape of the result 
  """
  if isinstance(symbolic_shape, Scalar): 
    return codegen.tuple([])

  shape_codegen = ShapeCodegen(codegen, input_exprs)
  return shape_codegen.visit(symbolic_shape)
  