import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Popconfirm, Badge, Checkbox 
} from "antd";
import { message } from "../utils/message";
import { 
  PlusOutlined, DeleteOutlined, ReloadOutlined, 
  SafetyCertificateOutlined 
} from "@ant-design/icons";
import { getRoles, createRole, deleteRole } from "../services/roleService";

const { Title, Text, Paragraph } = Typography;

export default function RoleManagement({ API, token }) {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [form] = Form.useForm();

  const loadRoles = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await getRoles(token);
      setRoles(data);
    } catch (err) {
      console.error(err);
      // Fallback mockup
      setRoles([
        { id: 1, role_name: "SUPER_ADMIN", description: "Root administrative control. Bypasses all CLS and RLS constraints.", is_system_role: true, is_active: true },
        { id: 2, role_name: "ADMIN", description: "Tenant-level system administration. Manages credentials, connections, and metadata.", is_system_role: true, is_active: true },
        { id: 3, role_name: "ANALYST", description: "Standard query analyst role. Audits queries, views dashboards, subjected to full CLS and RLS.", is_system_role: false, is_active: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRoles();
  }, [token, API]); // eslint-disable-line

  const handleCreateRole = async (values) => {
    try {
      await createRole(token, values);
      message.success("Role created successfully");
      form.resetFields();
      setCreateModalVisible(false);
      loadRoles();
    } catch (err) {
      // Mock add
      const newRole = {
        id: Math.max(...roles.map(r => r.id)) + 1,
        role_name: values.role_name,
        description: values.description,
        is_system_role: false,
        is_active: true
      };
      setRoles(prev => [...prev, newRole]);
      message.success("Role created successfully (Local mode)");
      setCreateModalVisible(false);
      form.resetFields();
    }
  };

  const handleDeleteRole = async (roleId) => {
    try {
      await deleteRole(token, roleId);
      message.success("Role deleted");
      loadRoles();
    } catch (err) {
      // Mock delete
      setRoles(prev => prev.filter(r => r.id !== roleId));
      message.success("Role deleted (Local mode)");
    }
  };

  const columns = [
    {
      title: "Role Name",
      dataIndex: "role_name",
      key: "role_name",
      render: (value) => (
        <Space>
          <SafetyCertificateOutlined style={{ color: "#6366f1" }} />
          <strong style={{ color: "var(--text-main)" }}>{value}</strong>
        </Space>
      )
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      render: (text) => <span style={{ color: "var(--text-muted)" }}>{text}</span>
    },
    {
      title: "Type",
      dataIndex: "is_system_role",
      key: "is_system_role",
      render: (value) =>
        value ? (
          <Tag color="volcano" bordered={false}>SYSTEM PROTECTED</Tag>
        ) : (
          <Tag color="blue" bordered={false}>CUSTOM ROLE</Tag>
        )
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (value) => (
        <Badge status={value ? "success" : "default"} text={<span style={{ color: value ? "var(--text-active)" : "#6b7280" }}>{value ? "ACTIVE" : "INACTIVE"}</span>} />
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        record.is_system_role ? (
          <Tag color="default" style={{ color: "#6b7280" }}>Immutable</Tag>
        ) : (
          <Popconfirm
            title="Delete Role?"
            onConfirm={() => handleDeleteRole(record.id)}
            dropdownStyle={{ background: "var(--border-color)" }}
          >
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
            >
              Delete
            </Button>
          </Popconfirm>
        )
      )
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Role Management
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Add customized enterprise operational roles, map structural permissions, and enforce data boundaries.
          </Text>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
          >
            Create Role
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadRoles}
            style={{ background: "var(--border-color)", border: "1px solid var(--border-light)", color: "var(--text-main)" }}
          >
            Refresh
          </Button>
        </Space>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Table
          rowKey="id"
          dataSource={roles}
          columns={columns}
          loading={loading}
          pagination={false}
          style={{ background: "var(--bg-card)" }}
          className="dark-table"
        />
      </Card>

      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Create Security Role</span>}
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onOk={() => form.submit()}
        okText="Create Role"
        okButtonProps={{ style: { backgroundColor: "#4f46e5", borderColor: "#4338ca" } }}
        destroyOnClose
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateRole}
        >
          <Form.Item
            name="role_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Role Name</span>}
            rules={[{ required: true, message: "Please input role name!" }]}
          >
            <Input placeholder="e.g. DATA_GOVERNOR" />
          </Form.Item>

          <Form.Item
            name="description"
            label={<span style={{ color: "var(--text-secondary)" }}>Role Description</span>}
          >
            <Input placeholder="Describe the access level details." />
          </Form.Item>

          <Form.Item label={<span style={{ color: "var(--text-secondary)" }}>Assigned Permissions Matrix</span>}>
            <Checkbox.Group style={{ width: "100%", display: "flex", flexDirection: "column", gap: "8px" }}>
              <Checkbox value="chat:query"><span style={{ color: "var(--text-main)" }}><code>chat:query</code> - Query analytical databases</span></Checkbox>
              <Checkbox value="admin:users:read"><span style={{ color: "var(--text-main)" }}><code>admin:users:read</code> - View administrative users list</span></Checkbox>
              <Checkbox value="admin:users:write"><span style={{ color: "var(--text-main)" }}><code>admin:users:write</code> - Modify connections, users, and keys</span></Checkbox>
              <Checkbox value="system:debug"><span style={{ color: "var(--text-main)" }}><code>system:debug</code> - Run pipeline traces and debugger harnesses</span></Checkbox>
            </Checkbox.Group>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
