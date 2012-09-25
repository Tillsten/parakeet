import syntax
import ast_conversion 
from function_registry import untyped_functions

class ReturnValue(Exception):
  def __init__(self, value):
    self.value = value 


class Closure:
  def __init__(self, fn, fixed_args):
    self.fn = fn 
    self.fixed_args = fixed_args

  
  
def eval_fn(fn, *args):
  n_expected = len(fn.args)
  n_given = len(args)
  assert n_expected == n_given , \
    "Expected %d args, given %d: %s" % (n_expected, n_given, args)
  env = dict(zip(fn.args, args)) 
  def eval_expr(expr):    
    def expr_Const():
      return expr.value
    def expr_Call():
      fn = eval_expr(expr.fn)
      arg_vals = map(eval_expr, expr.args)
      return fn(*arg_vals) 
    def expr_Prim():
      #assert False, expr.value.fn
       
      return expr.value.fn
    def expr_Var():
      return env[expr.name]
    def expr_Invoke():
      # for the interpreter Invoke and Call are identical since
      # we're dealing with runtime reprs for functions, prims, and 
      # closures which are just python Callables
      clos = eval_expr(expr.closure)
      arg_vals = map(eval_expr, expr.args)
      combined_arg_vals = clos.fixed_args + arg_vals
      return eval_fn(clos.fn, combined_arg_vals)
      
    def expr_Closure():
      fundef = untyped_functions[expr.fn]
      closure_arg_vals = map(eval_expr, expr.args) 
      return Closure(fundef, closure_arg_vals)
    
    functions = locals()
    nodetype =  expr.__class__.__name__
    fn_name = 'expr_' + nodetype
    return functions[fn_name]()
      
  def eval_merge_left(phi_nodes):
    for result, left, _ in phi_nodes:
      env[result] = eval_expr(left)
      
  def eval_merge_right(phi_nodes):
    for result, _, right in phi_nodes:
      env[result] = eval_expr(right)
       
  def eval_stmt(stmt):
    if isinstance(stmt, syntax.Return):
      v = eval_expr(stmt.value)
      raise ReturnValue(v)
    elif isinstance(stmt, syntax.Assign):
      env[stmt.lhs] = eval_expr(stmt.rhs)
    elif isinstance(stmt, syntax.If):
      cond_val = eval_expr(stmt.cond)
      if cond_val:
        eval_block(stmt.true)
        eval_merge_left(stmt.merge)
      else:
        eval_block(stmt.false)
        eval_merge_right(stmt.merge)
       
    else: 
      raise RuntimeError("Not implemented: %s" % stmt)
  def eval_block(stmts):
    for stmt in stmts:
      eval_stmt(stmt)
  try:
    
    #assert False, fn
    eval_block(fn.body)
  except ReturnValue as r:
    return r.value 
  except:
    raise
  
def run(python_fn, *args):
  untyped  = ast_conversion.translate_function_value(python_fn)
  # should eventually roll this up into something cleaner, since 
  # top-level functions are really acting like closures over their
  # global dependencies 
  global_args = [python_fn.func_globals[n] for n in untyped.nonlocals]
  all_args = global_args + list(args)
  return eval_fn(untyped, *all_args) 