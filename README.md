teapot
======

The idea behind teapot is to have a simple unittest script for
OpenStack POCs.  It's a really basic version of tempest.

https://github.com/openstack/tempest

Tempest is an essential component of CI/CD for large OpenStack
deployments or OpenStack development.  Teapot is a quick and dirty
alternative for basic testing.

Teapot also provides a simple illustration of how to use the python
OpenStack API for people who are learning how to program OpenStack.


== Usage ==

There are two "modes" of usage for teapot.  The first is an automatic
test run which loads each of the defined unit tests and runs them:


  [msolberg@localhost teapot]$ python teapot.py 
  KEYSTONE: services we expect to exist have entries in the catalog. ... ok
  KEYSTONE: we can create a tenant and a user associated with the tenant ... ok
  GLANCE: we can create an image ... ok
  NEUTRON: we can create a network ... ok
  NEUTRON: we can create a network with a subnet ... ok
  NEUTRON: we can create two networks with a router ... ok
  CINDER: Create a volume. ... ok
  CINDER: Create a volume from a glance image. ... ok
  NOVA: Launch a single instance. ... ok
  NOVA: Launch a single instance from a cinder volume. ... ok
  NOVA: Launch several instances attached to networks. ... ok
  
  ----------------------------------------------------------------------
  Ran 11 tests in 293.821s
  
  OK


To run teapot automatically, edit the global variables at the top of
the script to point it at your openstack installation's keystone
endpoint, turn on or off various components to test, and run the
script.

After running the automatic unit tests, you can run teapot in "manual"
mode.  This sets up an environment, pauses while you perform manual
testing, and then tears it down.

  [msolberg@localhost teapot]$ python teapot.py manual
  Creating environment for manual testing
  Environment created.  Tenant username is unittest and password is ef077c6f-2205-4684-8a8c-1502925e07f6
  Press enter to tear down the environment
  
  Tearing down environment
  Finished

