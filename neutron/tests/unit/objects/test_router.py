# Copyright (c) 2016 Intel Corporation.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from itertools import chain
from unittest import mock

import netaddr

from neutron_lib.db import api as db_api
from oslo_utils import uuidutils

from neutron.db import l3_attrs_db
from neutron.objects.qos import binding as qos_binding
from neutron.objects.qos import policy
from neutron.objects import router
from neutron.tests.unit.objects import test_base as obj_test_base
from neutron.tests.unit import testlib_api


class RouterRouteIfaceObjectTestCase(obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.RouterRoute


class RouterRouteDbObjectTestCase(obj_test_base.BaseDbObjectTestCase,
                                  testlib_api.SqlTestCase):

    _test_class = router.RouterRoute

    def setUp(self):
        super(RouterRouteDbObjectTestCase, self).setUp()
        self.update_obj_fields(
            {'router_id': lambda: self._create_test_router_id()})


class RouterExtraAttrsIfaceObjTestCase(obj_test_base.
                                       BaseObjectIfaceTestCase):
    _test_class = router.RouterExtraAttributes


class RouterExtraAttrsDbObjTestCase(obj_test_base.BaseDbObjectTestCase,
                                    testlib_api.SqlTestCase):
    _test_class = router.RouterExtraAttributes

    def setUp(self):
        super(RouterExtraAttrsDbObjTestCase, self).setUp()
        self.update_obj_fields(
            {'router_id': lambda: self._create_test_router_id()})


class RouterIfaceObjectTestCase(obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.Router


class RouterDbObjectTestCase(obj_test_base.BaseDbObjectTestCase,
                             testlib_api.SqlTestCase):

    _test_class = router.Router

    def setUp(self):
        super(RouterDbObjectTestCase, self).setUp()
        self.update_obj_fields(
            {'gw_port_id': lambda: self._create_test_port_id(),
             'flavor_id': lambda: self._create_test_flavor_id()})

    def _create_router(self, router_id, gw_port_id, project_id):
        r = router.Router(self.context,
                          id=router_id,
                          gw_port_id=gw_port_id,
                          project_id=project_id)
        r.create()

    def test_check_routers_not_owned_by_projects(self):
        for obj in self.obj_fields:
            self._create_router(router_id=obj['id'],
                                gw_port_id=obj['gw_port_id'],
                                project_id=obj['project_id'])
        obj = self.obj_fields[0]

        gw_port = obj['gw_port_id']
        project = obj['project_id']
        new_project = project

        gw_port_no_match = uuidutils.generate_uuid()
        project_no_match = uuidutils.generate_uuid()
        new_project_no_match = uuidutils.generate_uuid()

        # Check router match with gw_port BUT no projects
        router_exist = router.Router.check_routers_not_owned_by_projects(
            self.context,
            [gw_port],
            [project_no_match, new_project_no_match])
        self.assertTrue(router_exist)

        # Check router doesn't match with gw_port
        router_exist = router.Router.check_routers_not_owned_by_projects(
            self.context,
            [gw_port_no_match],
            [project])
        self.assertFalse(router_exist)

        # Check router match with gw_port AND project
        router_exist = router.Router.check_routers_not_owned_by_projects(
            self.context,
            [gw_port],
            [project, new_project_no_match])
        self.assertFalse(router_exist)

        # Check router match with gw_port AND new project
        router_exist = router.Router.check_routers_not_owned_by_projects(
            self.context,
            [gw_port],
            [project_no_match, new_project])
        self.assertFalse(router_exist)

        # Check router match with gw_port AND project AND new project
        router_exist = router.Router.check_routers_not_owned_by_projects(
            self.context,
            [gw_port],
            [project, new_project])
        self.assertFalse(router_exist)

    def test_qos_policy(self):
        _qos_policy_1 = self._create_test_qos_policy()
        _qos_policy_2 = self._create_test_qos_policy()

        self.obj_fields[0]['qos_policy_id'] = _qos_policy_1.id
        obj = self._test_class(
            self.context, **obj_test_base.remove_timestamps_from_fields(
                self.obj_fields[0], self._test_class.fields))
        obj.create()
        self.assertEqual(_qos_policy_1.id, obj.qos_policy_id)

        obj.qos_policy_id = _qos_policy_2.id
        obj.update()
        self.assertEqual(_qos_policy_2.id, obj.qos_policy_id)

        obj.qos_policy_id = None
        obj.update()
        self.assertIsNone(obj.qos_policy_id)

        obj.qos_policy_id = _qos_policy_1.id
        obj.update()
        router_id = obj.id
        gw_binding = qos_binding.QosPolicyRouterGatewayIPBinding.get_objects(
            self.context, router_id=router_id)
        self.assertEqual(1, len(gw_binding))
        self.assertEqual(_qos_policy_1.id, gw_binding[0].policy_id)
        obj.delete()
        gw_binding = qos_binding.QosPolicyRouterGatewayIPBinding.get_objects(
            self.context, router_id=router_id)
        self.assertEqual([], gw_binding)

    def test_object_version_degradation_1_1_to_1_0_no_qos_policy_id(self):
        self.objs[0].create()
        router_obj = self.objs[0]
        router_dict = router_obj.obj_to_primitive('1.1')
        self.assertIn('qos_policy_id', router_dict['versioned_object.data'])
        router_dict = router_obj.obj_to_primitive('1.0')
        self.assertNotIn('qos_policy_id', router_dict['versioned_object.data'])

    def test_get_router_ids_without_router_std_attrs(self):
        def create_r_attr_reg(idx):
            with db_api.CONTEXT_WRITER.using(self.context):
                router_db = {'id': self.objs[idx].id}
                l3_attrs_db.ExtraAttributesMixin.add_extra_attr(self.context,
                                                                router_db)

        for idx in range(3):
            self.objs[idx].create()
        expected_router_ids = [r.id for r in self.objs]

        for idx in range(3):
            router_ids = router.Router.\
                get_router_ids_without_router_std_attrs(self.context)
            self.assertEqual(expected_router_ids, router_ids)
            create_r_attr_reg(idx)
            expected_router_ids = expected_router_ids[1:]


class RouterPortIfaceObjectTestCase(obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.RouterPort


class RouterPortDbObjectTestCase(obj_test_base.BaseDbObjectTestCase,
                                 testlib_api.SqlTestCase):

    _test_class = router.RouterPort

    def setUp(self):
        super(RouterPortDbObjectTestCase, self).setUp()
        self.update_obj_fields(
            {'router_id': lambda: self._create_test_router_id(),
             'port_id': lambda: self._create_test_port_id()})


class DVRMacAddressIfaceObjectTestCase(obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.DVRMacAddress


class DVRMacAddressDbObjectTestCase(obj_test_base.BaseDbObjectTestCase,
                                    testlib_api.SqlTestCase):

    _test_class = router.DVRMacAddress


class FloatingIPIfaceObjectTestCase(obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.FloatingIP


class FloatingIPDbObjectTestCase(obj_test_base.BaseDbObjectTestCase,
                                 testlib_api.SqlTestCase):

    _test_class = router.FloatingIP

    def setUp(self):
        super(FloatingIPDbObjectTestCase, self).setUp()
        self.update_obj_fields(
            {'floating_port_id': lambda: self._create_test_port_id(),
             'fixed_port_id': lambda: self._create_test_port_id(),
             'router_id': lambda: self._create_test_router_id()})

    def test_qos_policy(self):
        _qos_policy_1 = self._create_test_qos_policy()
        _qos_policy_2 = self._create_test_qos_policy()

        self.obj_fields[0]['qos_policy_id'] = _qos_policy_1.id
        obj = self._test_class(
            self.context, **obj_test_base.remove_timestamps_from_fields(
                self.obj_fields[0], self._test_class.fields))
        obj.create()
        self.assertEqual(_qos_policy_1.id, obj.qos_policy_id)

        obj.qos_policy_id = _qos_policy_2.id
        obj.update()
        self.assertEqual(_qos_policy_2.id, obj.qos_policy_id)

        obj.qos_policy_id = None
        obj.update()
        self.assertIsNone(obj.qos_policy_id)

        obj.qos_policy_id = _qos_policy_1.id
        obj.update()
        fip_id = obj.id
        qos_fip_binding = qos_binding.QosPolicyFloatingIPBinding.get_objects(
            self.context, fip_id=fip_id)
        self.assertEqual(1, len(qos_fip_binding))
        self.assertEqual(_qos_policy_1.id, qos_fip_binding[0].policy_id)
        obj.delete()
        qos_fip_binding = qos_binding.QosPolicyFloatingIPBinding.get_objects(
            self.context, fip_id=fip_id)
        self.assertEqual([], qos_fip_binding)

    @mock.patch.object(policy.QosPolicy, 'unset_default')
    def test_qos_network_policy_id(self, *mocks):
        policy_obj = policy.QosPolicy(self.context)
        policy_obj.create()

        obj = self._make_object(self.obj_fields[0])
        obj.create()
        obj = router.FloatingIP.get_object(self.context, id=obj.id)
        self.assertIsNone(obj.qos_network_policy_id)
        self.assertIsNone(obj.qos_policy_id)

        network = self._create_test_network(qos_policy_id=policy_obj.id)
        self.update_obj_fields({'floating_network_id': network.id})
        obj = self._make_object(self.obj_fields[1])
        obj.create()
        obj = router.FloatingIP.get_object(self.context, id=obj.id)
        self.assertEqual(policy_obj.id, obj.qos_network_policy_id)
        self.assertIsNone(obj.qos_policy_id)

    def test_v1_1_to_v1_0_drops_qos_policy_id(self):
        obj = self._make_object(self.obj_fields[0])
        obj_v1_0 = obj.obj_to_primitive(target_version='1.0')
        self.assertNotIn('qos_policy_id', obj_v1_0['versioned_object.data'])

    def test_v1_2_to_v1_1_drops_qos_network_policy_id(self):
        obj = self._make_object(self.obj_fields[0])
        obj_v1_1 = obj.obj_to_primitive(target_version='1.1')
        self.assertNotIn('qos_network_policy_id',
                         obj_v1_1['versioned_object.data'])

    def test_get_scoped_floating_ips(self):
        def compare_results(router_ids, original_fips):
            self.assertCountEqual(
                original_fips,
                [
                    fip[0].id
                    for fip in router.FloatingIP.get_scoped_floating_ips(
                        self.context, router_ids)
                ]
            )

        # Setup three routers, networks and external networks
        routers = {}
        for i in range(3):
            router_id = self._create_test_router_id(name=f'router-{i}')
            routers[router_id] = []
            net_id = self._create_test_network_id()
            fip_net_id = self._create_external_network_id()

            # Create three subnets and three FIPs using the
            # aforementioned networks and routers
            for j in range(3):
                self._create_test_subnet_id(net_id)
                fip = router.FloatingIP(
                    self.context,
                    floating_ip_address=netaddr.IPAddress(f'10.{i}.{j}.3'),
                    floating_network_id=fip_net_id,
                    floating_port_id=self._create_test_port_id(
                        network_id=fip_net_id),
                    fixed_port_id=self._create_test_port_id(
                        network_id=net_id),
                    router_id=router_id,
                )
                fip.create()
                routers[router_id].append(fip.id)

        # For each router we created, fetch the fips and ensure the
        # results match what we originally created
        for router_id, original_fips in routers.items():
            compare_results([router_id], original_fips)

        # Now try to fetch all the fips for all the routers at once
        original_fips = list(chain.from_iterable(routers.values()))
        compare_results(routers.keys(), original_fips)


class DvrFipGatewayPortAgentBindingTestCase(
        obj_test_base.BaseObjectIfaceTestCase):

    _test_class = router.DvrFipGatewayPortAgentBinding
