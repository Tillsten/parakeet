import numpy as np 

import shape_inference
from shape_inference import call_shape_expr, unknown_scalar, const, array
from shape_inference import Shape, Var 
import parakeet 
import testing_helpers


def expect_shape(python_fn, args_list, expected):
  print "[expect_shape]"
  print " -- fn: ", python_fn
  print " -- args: ", args_list 
  typed_fn = parakeet.typed_repr(python_fn, args_list)
  print " -- types: ", typed_fn.input_types 
  result_shape = call_shape_expr(typed_fn)
  assert result_shape == expected, \
    "Expected shape %s, but got: %s" % (expected, result_shape) 

def const_scalar():
  return 1

def test_const_scalar():
  expect_shape(const_scalar, [], const(1))

def merge_scalars(b):
  if b:
    return 1
  else:
    return 2
  
def test_unknown_scalar():
  expect_shape(merge_scalars, [True], shape_inference.unknown_scalar)
  
def array_literal():
  return [1,2,3]

def test_array_literal():
  expect_shape(array_literal, [], array(3))

vec = np.array([1,2,3])
mat = np.array([[1,2,3],[4,5,6],[7,8,9]])

def ident(x):
  return x  

def test_ident():
  expect_shape(ident, [vec], array(Var(0)))
  expect_shape(ident, [mat], array(Var(0), Var(1)))
  
def increase_rank(x):
  return [x,x]

def test_increase_rank():
  expect_shape(increase_rank, [1], array(2))
  # TODO: 
  # Make these work by fixing assignment to slices 
  #
  # expect_shape(increase_rank, [vec], array(1, Var(0)))
  # expect_shape(increase_rank, [mat], array(1, Var(0), Var(1)))

def incr(xi):
  return xi + 1

from parakeet import each 

def simple_map(x):
  return each(incr, x, axis = 0)

def test_simple_map():
  expect_shape(simple_map, [vec], array(Var(0)))
  # TODO: Make axis = None result in nested maps 
  # expect_shape(simple_map, [mat], array(Var(0), Var(1)))

def map_increase_rank(x):
  return each(increase_rank, x, axis = 0)

def test_map_increase_rank():
  expect_shape(map_increase_rank, [vec], array(Var(0), 2))
  # TODO: this will work when slice assignment on LHS works 
  # expect_shape(simple_map, [mat], array(Var(0), Var(1)))


if __name__ == '__main__':
  testing_helpers.run_local_tests()