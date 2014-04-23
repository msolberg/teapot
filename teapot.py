"""
Copyright 2014, Michael Solberg <msolberg@redhat.com>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301  USA
"""

#### Imports

import unittest
import os, uuid, time, getopt, sys
import keystoneclient.v2_0.client as ksclient
from keystoneclient.exceptions import *
import glanceclient.v1.client as glanceclient
import neutronclient.v2_0.client as neutronclient
import cinderclient.v1.client as cinderclient
import novaclient.v1_1.client as novaclient

#### Defs

keystone_url='http://127.0.0.1:5000/v2.0'
admin_user='admin'
admin_pass='password'
admin_tenant='admin'
test_tenant='unittest tenant'
test_user='unittest'
test_timeout=300

# Whether or not to test individual components
TEST_KEYSTONE=True
TEST_GLANCE=True
TEST_NEUTRON=True
TEST_CINDER=True
TEST_NOVA=True

class TimeoutException(Exception):
    pass

class TestKeystone(unittest.TestCase):
    """Set of Keystone-specific tests"""
    def setUp(self):
        self.keystone = ksclient.Client(auth_url=keystone_url,
                                        username=admin_user,
                                        password=admin_pass,
                                        tenant_name=admin_tenant)
        self._tear_down_existing()
    
    def _tear_down_existing(self):
        """Try to delete any left over keystone artifacts"""
        try:
            u = self.keystone.users.find(name=test_user)
            self.keystone.users.delete(u)
        except:
            # This raises an exception if it can't find the user
            pass
        try:
            t = self.keystone.tenants.find(name=test_tenant)
            self.keystone.tenants.delete(t)
        except:
            pass

    def test_001_service_catalog(self):
        """KEYSTONE: services we expect to exist have entries in the catalog."""
        self.endpoints = []
        keystone_endpoint = self.keystone.service_catalog.url_for(service_type='identity',
                                                                  endpoint_type='publicURL')
        
        if TEST_GLANCE:
            glance_endpoint = self.keystone.service_catalog.url_for(service_type='image',
                                                                    endpoint_type='publicURL')
            self.endpoints.append(glance_endpoint)
        
        if TEST_NOVA:
            compute_endpoint = self.keystone.service_catalog.url_for(service_type='compute',
                                                                     endpoint_type='publicURL')
            self.endpoints.append(compute_endpoint)
        
        if TEST_NEUTRON:
            network_endpoint = self.keystone.service_catalog.url_for(service_type='network',
                                                                     endpoint_type='publicURL')
            self.endpoints.append(network_endpoint)
        
        for e in self.endpoints:
            self.assertTrue(e)
        
    def test_002_account_creation(self):
        """KEYSTONE: we can create a tenant and a user associated with the tenant"""
        t = self.keystone.tenants.create(test_tenant)
        u = self.keystone.users.create(test_user, str(uuid.uuid4()), "%s@redhat.com"% test_user, t.id)
        # This method loads the whole userlist.  Probably should skip this
        # for large directories.
        i = self.keystone.users.find(name=test_user)
        self.assertTrue(i.id)
        # Tear down the tenant.
        self.keystone.users.delete(u)
        self.keystone.tenants.delete(t)

class TestGlance(unittest.TestCase):
    """Set of Glance-specific tests"""
    def setUp(self):
        self.keystone = ksclient.Client(auth_url=keystone_url,
                                        username=admin_user,
                                        password=admin_pass,
                                        tenant_name=admin_tenant)
        self.endpoint = self.keystone.service_catalog.url_for(service_type='image',
                                                              endpoint_type='publicURL')
        self.glance = glanceclient.Client(endpoint=self.endpoint, token=self.keystone.auth_token)
    
    def test_001_create_image(self):
        """GLANCE: we can create an image"""
        self.image = self.glance.images.create(name='unittest image')
        self.assertTrue(self.image.id)
    
    def tearDown(self):
        self.glance.images.delete(self.image)

class TestNeutron(unittest.TestCase):
    """Set of Neutron specific tests"""
    def setUp(self):
        self.keystone = ksclient.Client(auth_url=keystone_url,
                                        username=admin_user,
                                        password=admin_pass,
                                        tenant_name=admin_tenant)
        self.t = self.keystone.tenants.create(test_tenant)
        self.password = str(uuid.uuid4())
        self.u = self.keystone.users.create(test_user, self.password, "%s@redhat.com"% test_user, self.t.id)
        self.endpoint = self.keystone.service_catalog.url_for(service_type='network',
                                                              endpoint_type='publicURL')
        self.keystone_testuser = ksclient.Client(auth_url=keystone_url,
                                        username=test_user,
                                        password=self.password,
                                        tenant_name=test_tenant)
        self.neutron = neutronclient.Client(endpoint_url=self.endpoint, token=self.keystone_testuser.auth_token)
        self._clean_tenant_networks()
        
    def _clean_tenant_networks(self):
        """Remove any network artifacts left over from failed tests in this tenant"""
        for p in self.neutron.list_ports().get('ports'):
            routerid = p.get('device_id')
            subnetid = p.get('fixed_ips')[0].get('subnet_id')
            try:
                self.neutron.remove_interface_router(routerid, {'subnet_id': subnetid})
            except:
                pass
        for r in self.neutron.list_routers().get('routers'):
            try:
                self.neutron.delete_router(r.get('id'))
            except:
                pass
        for s in self.neutron.list_subnets().get('subnets'):
            try:
                self.neutron.delete_subnet(s.get('id'))
            except:
                pass
        for n in self.neutron.list_networks().get('networks'):
            if not n.get('router:external'):
                try:
                    self.neutron.delete_network(n.get('id'))
                except:
                    pass
    
    def test_001_create_network(self):
        """NEUTRON: we can create a network"""
        network = {'name': 'test_001_network', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid = n.get('network', {}).get('id', None)
        self.assertTrue(netid)
    
    def test_002_create_network_with_subnet(self):
        """NEUTRON: we can create a network with a subnet"""
        network = {'name': 'test_002_network', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid = n.get('network', {}).get('id', None)
        subnet = {'name': 'test_002_subnet', 'network_id': netid, 'cidr': '192.168.250.0/24', 'ip_version': 4, 'gateway_ip': '192.168.250.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid = s.get('subnet', {}).get('id', None)
        self.assertTrue(subnetid)
    
    def test_003_create_router(self):
        """NEUTRON: we can create two networks with a router"""
        network1 = {'name': 'test_003_network1', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network1})
        netid1 = n.get('network', {}).get('id', None)
        subnet = {'name': 'test_003_subnet1', 'network_id': netid1, 'cidr': '192.168.251.0/24', 'ip_version': 4, 'gateway_ip': '192.168.251.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid1 = s.get('subnet', {}).get('id', None)
        network2 = {'name': 'test_003_network2', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network2})
        netid2 = n.get('network', {}).get('id', None)
        subnet = {'name': 'test_003_subnet2', 'network_id': netid2, 'cidr': '192.168.252.0/24', 'ip_version': 4, 'gateway_ip': '192.168.252.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid2 = s.get('subnet', {}).get('id', None)
        router = {'name': 'test_003_router1'}
        r = self.neutron.create_router({'router': router})
        routerid = r.get('router', {}).get('id', None)
        self.neutron.add_interface_router(routerid, {'subnet_id': subnetid1})
        self.neutron.add_interface_router(routerid, {'subnet_id': subnetid2})
        self.assertTrue(routerid)
    
    def tearDown(self):
        self._clean_tenant_networks()
        self.keystone.users.delete(self.u)
        self.keystone.tenants.delete(self.t)

class TestCinder(unittest.TestCase):
    """Set of Cinder-specific tests"""
    def setUp(self):
        self.keystone = ksclient.Client(auth_url=keystone_url,
                                        username=admin_user,
                                        password=admin_pass,
                                        tenant_name=admin_tenant)
        self.t = self.keystone.tenants.create(test_tenant)
        self.password = str(uuid.uuid4())
        self.u = self.keystone.users.create(test_user, self.password, "%s@redhat.com"% test_user, self.t.id)
        self.keystone_testuser = ksclient.Client(auth_url=keystone_url,
                                                 username=test_user,
                                                 password=self.password,
                                                 tenant_name=test_tenant)
        
        self.cinder = cinderclient.Client(test_user, self.password, test_tenant, keystone_url)
        if TEST_GLANCE:
            self.glance_endpoint = self.keystone.service_catalog.url_for(service_type='image',
                                                                         endpoint_type='publicURL')
            self.glance = glanceclient.Client(endpoint=self.glance_endpoint, token=self.keystone_testuser.auth_token)
    
    def test_001_create_volume(self):
        """CINDER: Create a volume."""
        self.testvol_001 = self.cinder.volumes.create(display_name="testvol_001", size=1)
        self.assertTrue(self.testvol_001.id)
        i = 0
        while (i < test_timeout):
            vol = self.cinder.volumes.find(id=self.testvol_001.id)
            if vol.status == u'available':
                break
            else:
                time.sleep(1)
                i = i + 1
        if vol.status != u'available':
            raise TimeoutException("Timeout waiting for volume creation")
    
    def test_002_create_volume_from_image(self):
        """CINDER: Create a volume from a glance image."""
        if TEST_GLANCE:
            # Pick the first image in the list and hope it's a good one.
            i = self.glance.images.list().next()
            self.testvol_002 = self.cinder.volumes.create(display_name="testvol_002", size=10, imageRef=i.id)
            self.assertTrue(self.testvol_002.id)
            i = 0
            while (i < test_timeout):
                vol = self.cinder.volumes.find(id=self.testvol_002.id)
                if vol.status == u'available':
                    break
                else:
                    time.sleep(1)
                    i = i + 1
            if vol.status != u'available':
                raise TimeoutException("Timeout waiting for volume creation")
        else:
            pass
    
    def tearDown(self):
        i = 0
        while (i < test_timeout):
            l = self.cinder.volumes.list()
            if len(l) == 0:
                break
            else:
                for v in self.cinder.volumes.list():
                    if v.status == u'available':
                        self.cinder.volumes.delete(v)
            time.sleep(1)
            i = i + 1
        l = self.cinder.volumes.list()
        if len(l) > 0:
            raise TimeoutException("Timeout waiting for volume deletion.")
        self.keystone.users.delete(self.u)
        self.keystone.tenants.delete(self.t)
    

class TestNova(unittest.TestCase):
    """Set of Nova-specific tests."""
    # Copied from TestNeutron
    def _clean_tenant_networks(self):
        """Remove any network artifacts left over from failed tests in this tenant"""
        for p in self.neutron.list_ports().get('ports'):
            routerid = p.get('device_id')
            subnetid = p.get('fixed_ips')[0].get('subnet_id')
            try:
                self.neutron.remove_interface_router(routerid, {'subnet_id': subnetid})
            except:
                pass
        for r in self.neutron.list_routers().get('routers'):
            try:
                self.neutron.delete_router(r.get('id'))
            except:
                pass
        for s in self.neutron.list_subnets().get('subnets'):
            try:
                self.neutron.delete_subnet(s.get('id'))
            except:
                pass
        for n in self.neutron.list_networks().get('networks'):
            if not n.get('router:external'):
                try:
                    self.neutron.delete_network(n.get('id'))
                except:
                    pass
    
    def setUp(self):
        self.keystone = ksclient.Client(auth_url=keystone_url,
                                        username=admin_user,
                                        password=admin_pass,
                                        tenant_name=admin_tenant)
        self.t = self.keystone.tenants.create(test_tenant)
        self.password = str(uuid.uuid4())
        self.u = self.keystone.users.create(test_user, self.password, "%s@redhat.com"% test_user, self.t.id)
        self.keystone_testuser = ksclient.Client(auth_url=keystone_url,
                                                 username=test_user,
                                                 password=self.password,
                                                 tenant_name=test_tenant)
        
        self.cinder = cinderclient.Client(test_user, self.password, test_tenant, keystone_url)
        neutron_endpoint = self.keystone.service_catalog.url_for(service_type='network',
                                                                 endpoint_type='publicURL')
        self.neutron = neutronclient.Client(endpoint_url=neutron_endpoint, token=self.keystone_testuser.auth_token)
        self.nova = novaclient.Client(test_user, self.password, test_tenant, keystone_url)
        with open(os.path.expanduser('~/.ssh/id_rsa.pub')) as fpubkey:
            self.nova.keypairs.create(name="mykey", public_key=fpubkey.read())
    
    def test_001_launch_single_instance(self):
        """NOVA: Launch a single instance."""
        f = self.nova.flavors.list()[1]
        i = self.nova.images.list()[0]
        network = {'name': 'nova_test_001_network', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid = n.get('network', {}).get('id', None)
        subnet = {'name': 'nova_test_001_subnet', 'network_id': netid, 'cidr': '192.168.250.0/24', 'ip_version': 4, 'gateway_ip': '192.168.250.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        instance = self.nova.servers.create(name='nova_test_001', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid}])
        self.assertTrue(instance)
    
    def test_002_launch_single_instance_with_cinder(self):
        """NOVA: Launch a single instance from a cinder volume."""
        f = self.nova.flavors.list()[1]
        i = self.nova.images.list()[0]
        network = {'name': 'nova_test_002_network', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid = n.get('network', {}).get('id', None)
        subnet = {'name': 'nova_test_002_subnet', 'network_id': netid, 'cidr': '192.168.251.0/24', 'ip_version': 4, 'gateway_ip': '192.168.251.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        t = self.cinder.volumes.create(display_name="nova_testvol_002", size=10, imageRef=i.id)
        # Need to wait for the volume to show up in the list here.
        timeout = 0
        while (timeout < test_timeout):
            vol = self.cinder.volumes.find(id=t.id)
            if vol.status == u'available':
                break
            else:
                time.sleep(1)
                timeout = timeout + 1
        instance = self.nova.servers.create(name='nova_test_002', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid}], block_device_mapping={'vda': "%s:"% t.id})
        self.assertTrue(instance)
    
    def test_003_multivm_with_networks(self):
        """NOVA: Launch several instances attached to networks."""
        f = self.nova.flavors.list()[1]
        i = self.nova.images.list()[0]
        
        network = {'name': 'nova_test_003_network1', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid1 = n.get('network', {}).get('id', None)
        subnet = {'name': 'nova_test_003_subnet1', 'network_id': netid1, 'cidr': '192.168.252.0/24', 'ip_version': 4, 'gateway_ip': '192.168.252.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid1 = s.get('subnet', {}).get('id', None)
        
        network = {'name': 'nova_test_003_network2', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid2 = n.get('network', {}).get('id', None)
        subnet = {'name': 'nova_test_003_subnet2', 'network_id': netid2, 'cidr': '192.168.253.0/24', 'ip_version': 4, 'gateway_ip': '192.168.253.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid2 = s.get('subnet', {}).get('id', None)
        
        network = {'name': 'nova_test_003_network3', 'admin_state_up': True}
        n = self.neutron.create_network({'network': network})
        netid3 = n.get('network', {}).get('id', None)
        subnet = {'name': 'nova_test_003_subnet3', 'network_id': netid3, 'cidr': '192.168.254.0/24', 'ip_version': 4, 'gateway_ip': '192.168.254.1'}
        s = self.neutron.create_subnet({'subnet': subnet})
        subnetid3 = s.get('subnet', {}).get('id', None)
        
        router = {'name': 'nova_test_003_router1'}
        r = self.neutron.create_router({'router': router})
        routerid = r.get('router', {}).get('id', None)
        self.neutron.add_interface_router(routerid, {'subnet_id': subnetid1})
        self.neutron.add_interface_router(routerid, {'subnet_id': subnetid2})
        
        instance1 = self.nova.servers.create(name='nova_test_003_001', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid1}])
        instance2 = self.nova.servers.create(name='nova_test_003_002', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid1}])
        instance3 = self.nova.servers.create(name='nova_test_003_003', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid1}])
        instance4 = self.nova.servers.create(name='nova_test_003_004', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid2}])
        instance5 = self.nova.servers.create(name='nova_test_003_005', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid2}])
        instance6 = self.nova.servers.create(name='nova_test_003_006', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid2}])
        instance7 = self.nova.servers.create(name='nova_test_003_007', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid3}])
        instance8 = self.nova.servers.create(name='nova_test_003_008', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid3}])
        instance9 = self.nova.servers.create(name='nova_test_003_009', image=i, flavor=f, key_name='mykey', nics=[{'net-id': netid3}])
    
    def tearDown(self):
        t = test_timeout
        while (t > 0):
            if self.nova.servers.list():
                for s in self.nova.servers.list():
                    try:
                        s.delete()
                    except:
                        pass
            else:
                break
            time.sleep(1)
            t = t - 1
        for v in self.cinder.volumes.list():
            if v.status == u'available':
                self.cinder.volumes.delete(v)
        self._clean_tenant_networks()
        self.keystone.users.delete(self.u)
        self.keystone.tenants.delete(self.t)

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], '')
        if "manual" in args:
             print "Creating environment for manual testing"
             tc = TestNova('test_003_multivm_with_networks')
             tc.setUp()
             tc.test_003_multivm_with_networks()
             print "Environment created.  Tenant username is %s and password is %s"% (test_user, tc.password)
             print "Press enter to tear down the environment"
             sys.stdin.readline()
             print "Tearing down environment"
             tc.tearDown()
             print "Finished"
             sys.exit()
    except:
        raise

    suites = []
    if TEST_KEYSTONE:
        suites.append(unittest.TestLoader().loadTestsFromTestCase(TestKeystone))
    if TEST_GLANCE:
        suites.append(unittest.TestLoader().loadTestsFromTestCase(TestGlance))
    if TEST_NEUTRON:
        suites.append(unittest.TestLoader().loadTestsFromTestCase(TestNeutron))
    if TEST_CINDER:
        suites.append(unittest.TestLoader().loadTestsFromTestCase(TestCinder))
    if TEST_NOVA:
        suites.append(unittest.TestLoader().loadTestsFromTestCase(TestNova))
    suite = unittest.TestSuite(suites)
    unittest.TextTestRunner(verbosity=2).run(suite)
