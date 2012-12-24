import syntax 
from syntax_visitor import SyntaxVisitor 

class FindLiveVars(SyntaxVisitor):
  def __init__(self):
    SyntaxVisitor.__init__(self)
    self.live_vars = set([])
    
  def visit_Var(self, expr):
    self.live_vars.add(expr.name)
    
  def visit_lhs(self, expr):
    if isinstance(expr, syntax.Var):
      pass 
    elif isinstance(expr, syntax.Tuple):
      for elt in expr.elts:
        self.visit_lhs(elt)
    else:
      self.visit_expr(expr)
      
  def visit_fn(self, fn):
    self.live_vars.clear()
    for name in fn.arg_names:
      self.live_vars.add(name)
    self.visit_block(fn.body)
    return self.live_vars

def find_live_vars(fn):
  return FindLiveVars().visit_fn(fn)

class VarUseCount(SyntaxVisitor):
  
  def __init__(self):
    
    SyntaxVisitor.__init__(self)
    self.counts = {}
    
  def visit_Var(self, expr):
    old_count = self.counts.get(expr.name, 0)
    self.counts[expr.name] = old_count + 1 
    
  def visit_lhs(self, expr):
    if isinstance(expr, syntax.Var):
      pass 
    elif isinstance(expr, syntax.Tuple):
      for elt in expr.elts:
        self.visit_lhs(elt)
    else:
      self.visit_expr(expr)
      
  def visit_fn(self, fn):
    self.counts.clear()
    for name in fn.arg_names:
      self.counts[name] = 1
    self.visit_block(fn.body)
    return self.counts 

def use_count(fn):
  return VarUseCount().visit_fn(fn)