import React, {
  useEffect,
  useState
} from "react";

import {
  Modal,
  Table,
  Button,
  Form,
  Input,
  Space,
  Tag,
  Popconfirm
} from "antd";
import { message } from "../utils/message";

import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined
} from "@ant-design/icons";

import {
  getRoles,
  createRole,
  deleteRole
} from "../services/roleService";

function RoleManagementModal({
  visible,
  onClose,
  token
}) {

  const [roles, setRoles] =
    useState([]);

  const [loading, setLoading] =
    useState(false);

  const [
    createModalVisible,
    setCreateModalVisible
  ] = useState(false);

  const [form] =
    Form.useForm();

  useEffect(() => {

    if (visible) {

      loadRoles();

    }

  }, [visible]);

  const loadRoles =
    async () => {

      try {

        setLoading(true);

        const data =
          await getRoles(token);

        setRoles(data);

      } catch {

        message.error(
          "Failed to load roles"
        );

      }

      setLoading(false);

    };

  const handleCreateRole =
    async () => {

      const values =
        await form.validateFields();

      try {

        await createRole(
          token,
          values
        );

        message.success(
          "Role created successfully"
        );

        form.resetFields();

        setCreateModalVisible(
          false
        );

        loadRoles();

      } catch {

        message.error(
          "Role creation failed"
        );

      }

    };

  const handleDeleteRole =
    async (roleId) => {

      try {

        await deleteRole(
          token,
          roleId
        );

        message.success(
          "Role deleted"
        );

        loadRoles();

      } catch {

        message.error(
          "Cannot delete role"
        );

      }

    };

  const columns = [
    {
      title: "ID",
      dataIndex: "id",
      width: 80
    },
    {
      title: "Role Name",
      dataIndex: "role_name",
      render: (value) => (
        <strong>{value}</strong>
      )
    },
    {
      title: "Description",
      dataIndex: "description"
    },
    {
      title: "Type",
      dataIndex: "is_system_role",
      render: (value) =>
        value ? (
          <Tag color="volcano">
            SYSTEM
          </Tag>
        ) : (
          <Tag color="blue">
            CUSTOM
          </Tag>
        )
    },
    {
      title: "Status",
      dataIndex: "is_active",
      render: (value) =>
        value ? (
          <Tag color="green">
            ACTIVE
          </Tag>
        ) : (
          <Tag>
            INACTIVE
          </Tag>
        )
    },
    {
      title: "Actions",
      render: (_, record) => (

        record.is_system_role ?

        <Tag color="red">
          Protected
        </Tag>

        :

        <Popconfirm
          title="Delete Role?"
          onConfirm={() =>
            handleDeleteRole(
              record.id
            )
          }
        >
          <Button
            danger
            icon={
              <DeleteOutlined />
            }
          >
            Delete
          </Button>
        </Popconfirm>
      )
    }
  ];

  return (
    <>
      <Modal
        title="Role Management"
        open={visible}
        footer={null}
        onCancel={onClose}
        width={900}
      >

        <div
          style={{
            marginBottom: 16,
            display: "flex",
            justifyContent:
              "space-between"
          }}
        >

          <Space>

            <Button
              type="primary"
              icon={
                <PlusOutlined />
              }
              onClick={() =>
                setCreateModalVisible(
                  true
                )
              }
            >
              Create Role
            </Button>

            <Button
              icon={
                <ReloadOutlined />
              }
              onClick={loadRoles}
            >
              Refresh
            </Button>

          </Space>

        </div>

        <Table
          rowKey="id"
          dataSource={roles}
          columns={columns}
          loading={loading}
          bordered
        />

      </Modal>

      <Modal
        title="Create Role"
        open={createModalVisible}
        onCancel={() =>
          setCreateModalVisible(
            false
          )
        }
        onOk={handleCreateRole}
      >

        <Form
          form={form}
          layout="vertical"
        >

          <Form.Item
            name="role_name"
            label="Role Name"
            rules={[
              {
                required: true
              }
            ]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description"
          >
            <Input />
          </Form.Item>

        </Form>

      </Modal>
    </>
  );
}

export default RoleManagementModal;