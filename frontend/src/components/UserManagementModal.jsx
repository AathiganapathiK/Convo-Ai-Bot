import React, { useState } from "react";
import {
  Modal,
  Table,
  Button,
  Tag,
  Space,
  Popconfirm,
  Form,
  Input,
  Select
} from "antd";
import {
  UserAddOutlined,
  EditOutlined,
  UnlockOutlined,
  LockOutlined,
  ReloadOutlined
} from "@ant-design/icons";

const { Option } = Select;

function UserManagementModal({
  visible,
  onClose,
  users,
  loadUsers,
  onCreateUser,
  onUpdateUser,
  onToggleStatus
}) {
  const [createFormVisible, setCreateFormVisible] = useState(false);
  const [editFormVisible, setEditFormVisible] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  // Columns for Users Table
  const columns = [
    {
      title: "ID",
      dataIndex: "id",
      key: "id",
      width: 60,
    },
    {
      title: "Full Name",
      dataIndex: "full_name",
      key: "full_name",
      render: (text) => <span style={{ fontWeight: 600 }}>{text}</span>,
    },
    {
      title: "Employee ID",
      dataIndex: "employee_id",
      key: "employee_id",
    },
    {
      title: "Department",
      dataIndex: "department",
      key: "department",
      render: (dept) => <Tag color="geekblue">{dept}</Tag>,
    },
    {
      title: "Role",
      dataIndex: "role",
      key: "role",
      render: (role) => (
        <Tag color={role?.toUpperCase() === "ADMIN" ? "volcano" : "blue"}>
          {role}
        </Tag>
      ),
    },
    {
      title: "Assigned Roles",
      dataIndex: "user_roles",
      render: (roles) => {

        if (!roles?.length)
          return "-";

        return roles.map(
          (role) => (
            <Tag
              key={role}
              color="blue"
            >
              {role}
            </Tag>
          )
        );
      }
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive) => (
        <Tag color={isActive ? "success" : "default"}>
          {isActive ? "ACTIVE" : "INACTIVE"}
        </Tag>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space size="middle">
          <Button
            type="text"
            icon={<EditOutlined style={{ color: "#1890ff" }} />}
            onClick={() => handleOpenEdit(record)}
          >
            Edit
          </Button>

          <Popconfirm
            title={`${record.is_active ? "Deactivate" : "Activate"} this user?`}
            onConfirm={() => onToggleStatus(record.id, record.is_active)}
            okText="Yes"
            cancelText="No"
          >
            <Button
              type="text"
              danger={record.is_active}
              icon={record.is_active ? <LockOutlined /> : <UnlockOutlined style={{ color: "#52c41a" }} />}
            >
              {record.is_active ? "Deactivate" : "Activate"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleOpenEdit = (user) => {
    setEditingUser(user);
    editForm.setFieldsValue({
      full_name: user.full_name,
      department: user.department,
      role: user.role,
      company: user.company || "ABC Corp",
      location: user.location || "",
      mobile_number: user.mobile_number || "",
      address: user.address || "",
    });
    setEditFormVisible(true);
  };

  const handleCreateSubmit = () => {
    createForm.validateFields().then((values) => {
      const payload = {
        ...values,
        username: values.official_email,
        password: ""
      };
      onCreateUser(payload).then(() => {
        setCreateFormVisible(false);
        createForm.resetFields();
      });
    });
  };

  const handleEditSubmit = () => {
    editForm.validateFields().then((values) => {
      onUpdateUser({ ...editingUser, ...values }).then(() => {
        setEditFormVisible(false);
        setEditingUser(null);
      });
    });
  };

  return (
    <Modal
      title="User Management Panel"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={1000}
      style={{ top: 50 }}
    >
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <Space>
          <Button
            type="primary"
            icon={<UserAddOutlined />}
            onClick={() => setCreateFormVisible(true)}
            style={{ borderRadius: "6px" }}
          >
            Add New User
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadUsers}
            style={{ borderRadius: "6px" }}
          >
            Refresh List
          </Button>
        </Space>
      </div>

      <Table
        dataSource={users}
        columns={columns}
        rowKey="id"
        bordered
        pagination={{ pageSize: 8 }}
        size="small"
        style={{ marginTop: "10px" }}
      />

      {/* CREATE USER MODAL */}
      <Modal
        title="Create New User"
        open={createFormVisible}
        onCancel={() => setCreateFormVisible(false)}
        onOk={handleCreateSubmit}
        okText="Create User"
        destroyOnClose
      >
        <Form
          form={createForm}
          layout="vertical"
          initialValues={{ role: "ANALYST", company: "ABC Corp" }}
          style={{ marginTop: "15px" }}
        >
          <Form.Item
            name="employee_id"
            label="Employee ID"
            rules={[{ required: true, message: "Please input Employee ID!" }]}
          >
            <Input placeholder="e.g. EMP1004" />
          </Form.Item>

          <Form.Item
            name="full_name"
            label="Full Name"
            rules={[{ required: true, message: "Please input Full Name!" }]}
          >
            <Input placeholder="e.g. John Doe" />
          </Form.Item>

          <Form.Item
            name="official_email"
            label="Official Email"
            rules={[
              { required: true, message: "Please input official email!" },
              { type: "email", message: "Please enter a valid email!" }
            ]}
          >
            <Input placeholder="john.doe@company.com" />
          </Form.Item>

          <Form.Item
            name="department"
            label="Department"
            rules={[{ required: true, message: "Please input department!" }]}
          >
            <Input placeholder="e.g. Sales, Finance, Admin" />
          </Form.Item>

          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select>
              <Option value="ANALYST">ANALYST</Option>
              <Option value="ADMIN">ADMIN</Option>
            </Select>
          </Form.Item>

          <Form.Item name="company" label="Company">
            <Input placeholder="ABC Corp" />
          </Form.Item>
        </Form>
      </Modal>

      {/* EDIT USER MODAL */}
      <Modal
        title="Edit User Details"
        open={editFormVisible}
        onCancel={() => {
          setEditFormVisible(false);
          setEditingUser(null);
        }}
        onOk={handleEditSubmit}
        okText="Save Changes"
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: "15px" }}>
          <Form.Item
            name="full_name"
            label="Full Name"
            rules={[{ required: true, message: "Please input full name!" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="department"
            label="Department"
            rules={[{ required: true, message: "Please input department!" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select>
              <Option value="ANALYST">ANALYST</Option>
              <Option value="ADMIN">ADMIN</Option>
              <Option value="USER">USER</Option>
            </Select>
          </Form.Item>

          <Form.Item name="company" label="Company">
            <Input />
          </Form.Item>

          <Form.Item name="location" label="Location">
            <Input placeholder="e.g. New York, London" />
          </Form.Item>

          <Form.Item name="mobile_number" label="Mobile Number">
            <Input placeholder="e.g. +1 555-0199" />
          </Form.Item>

          <Form.Item name="address" label="Address">
            <Input placeholder="Street address details" />
          </Form.Item>
        </Form>
      </Modal>
    </Modal>
  );
}

export default UserManagementModal;
