import llvm.core as llcore
from llvm.core import Type as lltype
from llvm.core import Builder 

import ptype
import prims 
import syntax
from common import dispatch  
from function_registry import typed_functions, ClosureSignatures 

import llvm_types
from llvm_types import llvm_value_type, llvm_ref_type
import llvm_context 
from llvm_compiled_fn import CompiledFn
import llvm_prims 
 


def const(python_scalar, parakeet_type):
  assert isinstance(parakeet_type, ptype.ScalarT)
  llvm_type = llvm_value_type(parakeet_type)
  if isinstance(parakeet_type, ptype.FloatT):
    return llcore.Constant.real(llvm_type, python_scalar)
  else:
    return llcore.Constant.int(llvm_type, python_scalar)

def int32(x):
  return const(x, ptype.Int32)

def init_llvm_vars(fundef, llvm_fn, builder):
  env = {}  
  for (name, t) in fundef.type_env.iteritems():
    llvm_t = llvm_ref_type(t)
    stack_val = builder.alloca(llvm_t, name)
    env[name] = stack_val 

  for llvm_arg, parakeet_arg in zip(llvm_fn.args, fundef.args):
    if isinstance(parakeet_arg, str):
      name = parakeet_arg
    elif isinstance(parakeet_arg, syntax.Var):
      name = parakeet_arg.name
    else:
      assert False, "Tuple arg patterns not yet implemented"
    llvm_arg.name = name
    # store the value of the input in the stack value we've already allocated
    # for the input var 
    builder.store(llvm_arg, env[name])
     

  # tell the builder to start inserting 
  return env 


compiled_functions = {}

def compile_fn(fundef):
  if fundef.name in compiled_functions:
    return compiled_functions[fundef.name]
  
  # contexts bundle together the module and pass manager
  # just be sure to use the same context when you register
  # the function and run optimizations! 
  context = llvm_context.opt_context
  
  llvm_input_types = map(llvm_ref_type, fundef.input_types)
  llvm_output_type = llvm_ref_type(fundef.return_type)
  llvm_fn_t = lltype.function(llvm_output_type, llvm_input_types)
  llvm_fn = context.module.add_function(llvm_fn_t, fundef.name)
    
  def new_block(name):
    bb = llvm_fn.append_basic_block(name)
    builder = Builder.new(bb)
    return bb, builder 
 
  _, start_builder = new_block("entry")
  env = init_llvm_vars(fundef, llvm_fn, start_builder)
  


  
  def compile_expr(expr, builder):
    
    #print "compile_expr", expr 
    def compile_Var():
      ref =  env[expr.name]
      val = builder.load(ref, expr.name + "_val")
      return val 
    def compile_Const():
      assert isinstance(expr.type, ptype.ScalarT)
      return const(expr.value, expr.type)
    
    def compile_Cast():
      llvm_value = compile_expr(expr.value, builder)
      return llvm_types.convert(llvm_value, expr.value.type, expr.type, builder)
    
    def compile_Closure():
      # allocate a length 3 array
      # - the first element is a distinct id for each (untyped function, type list) pair
      # - the second element is array partially applied arguments
      
      closure_t = expr.type
      assert isinstance(closure_t, ptype.ClosureT)
      llvm_closure_t = llvm_value_type(closure_t)
      closure_object =  builder.malloc(llvm_closure_t, "closure_object")
      #print "malloc closure", closure_object
      id_slot = builder.gep(closure_object, [int32(0), int32(0)], "closure_id_slot")
      #print "get id slot", id_slot
      closure_num = ClosureSignatures.get_id(closure_t)
      builder.store(const(closure_num, ptype.Int64), id_slot)
       
      assert len(closure_t.args) == 0, "Code generation for closure args not yet implemented"
      return closure_object  
    
    def compile_Invoke():
      closure_object = compile_expr(expr.closure, builder)

      arg_types = [arg.type for arg in expr.args] 
      
      closure_t = expr.closure.type
      assert isinstance(closure_t, ptype.ClosureT)
      
      #closure_id_slot = builder.gep(llvm_closure_object, [const(0), const(0)], "closure_id_slot")
      #actual_closure_id = builder.load(closure_id_slot)
      
      # get the int64 identifier which maps to an untyped_fn/arg_types pairs
      
      untyped_fn_id = closure_t.fn
      assert isinstance(untyped_fn_id, str), "Expected %s to be string identifier" % (untyped_fn_id)
      full_arg_types = closure_t.args + tuple(arg_types)
      # either compile the function we're about to invoke or get its compiled form from a cache
      key = (untyped_fn_id, full_arg_types)
      typed_fundef = typed_functions[key]
      target_fn_info = compile_fn(typed_fundef)
      target_fn = target_fn_info.llvm_fn 
        
      llvm_closure_args = []
      
      closure_args_slot = builder.gep(closure_object, [int32(0), int32(1)], "closure_args_slot")
      closure_args_array = builder.load(closure_args_slot, "closure_args")
      for (closure_arg_idx, _) in enumerate(closure_t.args):
        arg_ptr = builder.gep(closure_args_array, [const(closure_arg_idx)], "closure_arg%d_ptr" % closure_arg_idx)
        arg = builder.load(arg_ptr, "closure_arg%d" % closure_arg_idx)
        llvm_closure_args.append(arg)
      
      full_args_list = llvm_closure_args + [compile_expr(arg, builder) for arg in expr.args]
      assert len(full_args_list) == len(full_arg_types)  
      call =  builder.call(target_fn, full_args_list, "invoke_result")
      # print "Call", call 
      return call 
    
    def compile_PrimCall():
      prim = expr.prim
      args = expr.args 
      
      # type specialization should have made types of arguments uniform, 
      # so we only need to check the type of the first arg 
      t = args[0].type
      
      llvm_args = [compile_expr(arg, builder) for arg in args]
      
      result_name = prim.name + "_result"
      
      if isinstance(prim, prims.Cmp):
        x, y = llvm_args 
        if isinstance(t, ptype.FloatT):
          cmp_op = llvm_prims.float_comparisons[prim]
          return builder.fcmp(cmp_op, x, y, result_name)
        elif isinstance(t, ptype.SignedT):
          cmp_op = llvm_prims.signed_int_comparisons[prim]
          return builder.icmp(cmp_op, x, y, result_name)
        else:
          assert isinstance(t, ptype.UnsignedT), "Unexpected type: %s" % t
          cmp_op = llvm_prims.unsigned_int_comparisons[prim]
          return builder.icmp(cmp_op, x, y, result_name)
      elif isinstance(prim, prims.Arith) or isinstance(prim, prims.Bitwise):
        if isinstance(t, ptype.FloatT):
          instr = llvm_prims.float_binops[prim]
        elif isinstance(t, ptype.SignedT):
          instr = llvm_prims.signed_binops[prim]
        elif isinstance(t, ptype.UnsignedT):
          instr = llvm_prims.unsigned_binops[prim]  
        return getattr(builder, instr)(name = "%s_result" % prim.name, *llvm_args)
      else:
        assert False, "UNSUPPORTED PRIMITIVE: %s" % expr 
     
    return dispatch(expr, "compile")
    
  def get_ref(expr):
    # for now only get references to variables
    assert isinstance(expr, syntax.Var)
    return env[expr.name]
      
  def compile_merge_left(phi_nodes, builder):
    for name, (left, _) in phi_nodes.iteritems():
      ref = env[name]
      value = compile_expr(left, builder)
      builder.store(value, ref)
       
      
  def compile_merge_right(phi_nodes, builder):
    for name, (_, right) in phi_nodes.iteritems():
      ref = env[name]
      value = compile_expr(right, builder)
      builder.store(value, ref)
       
    
  def compile_stmt(stmt, builder):
    """Translate an SSA statement into llvm. Every translation
    function returns a builder pointing to the end of the current 
    basic block and a boolean indicating whether every branch of 
    control flow in that statement ends in a return. 
    The latter is needed to avoid creating empty basic blocks, 
    which were causing some mysterious crashes inside LLVM"""
    if isinstance(stmt, syntax.Assign):
      
      ref = get_ref(stmt.lhs)
      value = compile_expr(stmt.rhs, builder)
      #print "ASSIGN"
      #print "LHS %s : %s" % (ref, ref.type)
      #print "RHS %s : %s" % (value, value.type)
      builder.store(value, ref)
       
      return builder, False 
    elif isinstance(stmt, syntax.While):
      # current flow ----> loop --------> exit--> after  
      #    |                       skip------------|
      #    |----------------------/
      compile_merge_left(stmt.merge_before, builder)
      loop_bb, loop_builder = new_block("loop_body")
      
      skip_bb, skip_builder = new_block("skip_loop")
      after_bb, after_builder = new_block("after_loop")
      enter_cond = compile_expr(stmt.cond, builder)
      builder.cbranch(enter_cond, loop_bb, skip_bb)
      _, body_always_returns = compile_block(stmt.body, loop_builder)
      if not body_always_returns:
        exit_bb, exit_builder = new_block("loop_exit")
        compile_merge_right(stmt.merge_before, loop_builder)
        repeat_cond = compile_expr(stmt.cond, loop_builder)
        loop_builder.cbranch(repeat_cond, loop_bb, exit_bb)
        compile_merge_right(stmt.merge_after, exit_builder)
        exit_builder.branch(after_bb)
      compile_merge_left(stmt.merge_after, skip_builder)
      skip_builder.branch(after_bb)
      return after_builder, False 
 
    elif isinstance(stmt, syntax.Return):
      builder.ret(compile_expr(stmt.value, builder))
      return builder, True 
    elif isinstance(stmt, syntax.If):
      cond = compile_expr(stmt.cond, builder)
      
      # compile the two possible branches as distinct basic blocks
      # and then wire together the control flow with branches
      true_bb, true_builder = new_block("if_true")
      _, true_always_returns = compile_block(stmt.true, true_builder)
      
      false_bb, false_builder = new_block("if_false")
      _, false_always_returns = compile_block(stmt.false, false_builder)
      
      # did both branches end in a return? 
      both_always_return = true_always_returns and false_always_returns 

      builder.cbranch(cond, true_bb, false_bb)
      # compile phi nodes as assignments and then branch
      # to the continuation block 
      compile_merge_left(stmt.merge, true_builder)
      compile_merge_right(stmt.merge, false_builder)
      
      # if both branches return then there is no point
      # making a new block for more code 
      if both_always_return:

        return None, True 
      else:
        after_bb, after_builder = new_block("if_after")
        if not true_always_returns:
          true_builder.branch(after_bb)
        if not false_always_returns:
          false_builder.branch(after_bb)      
        return after_builder, False  
  
  def compile_block(stmts, builder = None):
    # print "compile_block", stmts
    for stmt in stmts:
      builder, always_returns = compile_stmt(stmt, builder)

      if always_returns:
        return builder, True 
    return builder, False

  compile_block(fundef.body, start_builder)
  context.run_passes(llvm_fn)
  
  result = CompiledFn(llvm_fn, fundef) 
  compiled_functions[fundef.name] = result 
  #print result.llvm_fn  
  
  return result 
