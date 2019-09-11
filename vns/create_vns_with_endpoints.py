"""
Description
-----------

Creates AOS virtual networks (VN) with server endpoints.

Demonstrates use of graph queries in QE and QL formats.

Expected user input
-------------------

Environment variables:

 - AOS_URL - URL of AOS instance (e.g. https://172.10.200.3)
 - AOS_BLUEPRINT_ID - blueprint UUID where VNs will be created

"""

import os
import requests


def create_vn_sample():
    username = os.environ.get("AOS_USERNAME", "admin")
    password = os.environ.get("AOS_PASSWORD", "admin")
    aos_url = os.environ.get("AOS_URL")
    bp_id = os.environ.get("AOS_BLUEPRINT_ID")
    vn_gateway = "10.0.0.1"
    vn_subnet = "10.0.0.0/24"

    vn_label = "test_vn_api"
    vn_desc = "test VN API"
    vlan_id = 1234

    assert aos_url
    assert bp_id

    print("Authenticating with AOS at {aos_url}".format(aos_url=aos_url))

    auth_resp = requests.post(
        "{aos_url}/api/aaa/login".format(aos_url=aos_url),
        json={"username": username, "password": password},
        verify=False,
    )

    assert auth_resp.ok, auth_resp

    token = auth_resp.json()["token"]

    get_leaf_nodes_query = """
    {
        system_nodes(role: "leaf") {
          id, system_id, label, role
        }
    }
    """
    leafs_resp = requests.post("{aos_url}/api/blueprints/{bp_id}/ql-readonly".format(
            aos_url=aos_url,
            bp_id=bp_id
        ),
        json={"query": get_leaf_nodes_query},
        headers={"AuthToken": token},
        verify=False,
    )

    assert leafs_resp.ok

    leafs = leafs_resp.json()["data"]["system_nodes"]

    print("Leaf nodes: {leafs}".format(leafs=", ".join(l["label"] for l in leafs)))

    assert leafs

    first_leaf = leafs[0]

    servers_connected_to_leaf_graph_query = """
    node(name="leaf", type="system", role="leaf", deploy_mode="deploy", system_id="{leaf_sys_id}")\
      .out("hosted_interfaces")\
      .node(name="leaf_interface", type="interface")\
      .out("link")\
      .node(type="link", name="link", deploy_mode="deploy")\
      .in_("link")\
      .node(type="interface", name="srv_interface")\
      .in_("hosted_interfaces")\
      .node(name="srv", type="system", role=is_in(["l2_server", "l3_server"]))
    """.format(leaf_sys_id=first_leaf["system_id"]).replace("\n", "").strip()

    srv_interfaces_resp = requests.post(
        "{aos_url}/api/blueprints/{bp_id}/qe".format(
            aos_url=aos_url,
            bp_id=bp_id
        ),
        json={"query": servers_connected_to_leaf_graph_query},
        headers={"AuthToken": token},
        verify=False,
    )

    assert srv_interfaces_resp.ok, srv_interfaces_resp.json()

    server_interfaces = [
        (item["srv"], item["srv_interface"])
        for item in srv_interfaces_resp.json()["items"]
    ]
    print("server interfaces for leaf {leaf}: {interface_names}".format(
        leaf=first_leaf["label"], interface_names=", ".join(
            "{}: {}".format(srv["label"], iface["if_name"])
            for srv, iface in server_interfaces
        )
    ))

    print("Create VN {label}".format(label=vn_label))
    vn_spec = {
        "label": vn_label,
        "description": vn_desc,
        "vn_type": "vxlan",
        "bound_to": [{"system_id": first_leaf["id"], "vlan_id": vlan_id}],
        "l3_connectivity": "l3Enabled",
        "virtual_gateway_ipv4": vn_gateway,
        "ipv4_subnet": vn_subnet,
        "ipv4_enabled": True,
        "dhcp_service": None,
    }

    vn_create_resp = requests.post(
        "{aos_url}/api/blueprints/{bp_id}/virtual-networks".format(
            aos_url=aos_url,
            bp_id=bp_id
        ),
        json=vn_spec,
        headers={"AuthToken": token},
        verify=False,
    )

    assert vn_create_resp.ok, vn_create_resp.json()

    vn = vn_create_resp.json()
    print("VN created: {vn}".format(vn=vn))
    vn_id = vn["id"]

    assert server_interfaces

    for srv, server_iface in server_interfaces:
        server_iface_id = server_iface["id"]

        print("Add server interface {srv}:{srv_iface_name} ({srv_iface}) to VN {vn_id}".format(
            srv=srv["hostname"],
            srv_iface_name=server_iface["if_name"],
            srv_iface=server_iface_id,
            vn_id=vn_id,
        ))

        new_endpoint = {
            "interface_id": server_iface_id,
            "label": "test_vn_endpoint",
            "tag_type": "vlan_tagged",
        }

        add_endpoint_resp = requests.patch(
            "{aos_url}/api/blueprints/{bp_id}/virtual-networks/{vn_id}".format(
                aos_url=aos_url,
                bp_id=bp_id,
                vn_id=vn_id,
            ),
            json={"endpoints": [new_endpoint]},
            headers={"AuthToken": token},
            verify = False,
        )

        assert add_endpoint_resp.ok, add_endpoint_resp.json()


if __name__ == '__main__':
    create_vn_sample()
