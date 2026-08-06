import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, Popconfirm, message, Badge, Row, Col, Spin 
} from "antd";
import { 
  UserAddOutlined, EditOutlined, LockOutlined, UnlockOutlined, 
  ReloadOutlined, MailOutlined, SearchOutlined
} from "@ant-design/icons";
import { getUserRoles } from "../services/userRoleService";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function UserManagement({ API, token, userInfo }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [createFormVisible, setCreateFormVisible] = useState(false);
  const [editFormVisible, setEditFormVisible] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [companiesList, setCompaniesList] = useState([]);
  
  // Search and Filter States
  const [searchText, setSearchText] = useState("");
  const [filterRole, setFilterRole] = useState("ALL");
  const [filterStatus, setFilterStatus] = useState("ALL");

  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const loadUsers = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const response = await fetch(`${API}/admin/users`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        const enrichedUsers = await Promise.all(
          data.map(async (user) => {
            try {
              const roles = await getUserRoles(token, user.employee_id);
              return { ...user, user_roles: roles };
            } catch {
              return { ...user, user_roles: [] };
            }
          })
        );
        setUsers(enrichedUsers);
      } else {
        message.error("Failed to load users from server");
      }
    } catch (error) {
      console.error(error);
      message.error("Error connecting to server. Local backup loaded.");
      // Fallback for demo/offline validation
      setUsers([
        {
          id: 1,
          full_name: "Sarah Jenkins",
          employee_id: "EMP1001",
          official_email: "sarah.jenkins@company.com",
          department: "Sales",
          role: "ADMIN",
          company: "Acme Retail",
          user_roles: ["SUPER_ADMIN", "ADMIN"],
          is_active: true
        },
        {
          id: 2,
          full_name: "Marcus Vance",
          employee_id: "EMP1002",
          official_email: "marcus.vance@company.com",
          department: "Finance",
          role: "ANALYST",
          company: "Acme Retail",
          user_roles: ["ANALYST"],
          is_active: true
        },
        {
          id: 3,
          full_name: "Elena Rostova",
          employee_id: "EMP1003",
          official_email: "elena.rostova@company.com",
          department: "Operations",
          role: "ANALYST",
          company: "Acme Retail",
          user_roles: [],
          is_active: false
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const loadCompanies = async () => {
    if (!token) return;
    try {
      const response = await fetch(`${API}/companies`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setCompaniesList(data);
      }
    } catch (error) {
      console.error("Error loading companies:", error);
    }
  };

  useEffect(() => {
    loadUsers();
    loadCompanies();
  }, [token, API]); // eslint-disable-line

  const onCreateUser = async (userData) => {
    try {
      const response = await fetch(`${API}/admin/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(userData)
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to create user");
      }

      message.success("User Created Successfully");
      loadUsers();
      return true;
    } catch (error) {
      console.error(error);
      message.error(error.message || "Failed to connect to security server");
      return false;
    }
  };

  const onUpdateUser = async (userData) => {
    try {
      const response = await fetch(`${API}/admin/users/${userData.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          full_name: userData.full_name,
          department: userData.department,
          role: userData.role,
          company: userData.company,
          location: userData.location,
          mobile_number: userData.mobile_number,
          address: userData.address,
          division_code: userData.division_code || null
        })
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to update user");
      }

      message.success("User updated successfully");
      loadUsers();
      return true;
    } catch (error) {
      console.error(error);
      message.error(error.message || "Failed to connect to security server");
      return false;
    }
  };

  const onToggleStatus = async (userId, currentStatus) => {
    try {
      const response = await fetch(`${API}/admin/users/${userId}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ is_active: !currentStatus })
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to update status");
      }

      message.success("User status updated");
      loadUsers();
    } catch (error) {
      console.error(error);
      message.error(error.message || "Failed to connect to security server");
    }
  };

  // UI authorization check
  if (!userInfo) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "400px" }}>
        <Spin size="large" tip="Loading User Settings..." />
      </div>
    );
  }

  const userRole = userInfo.role?.toUpperCase();
  if (userRole !== "SYSTEM_ADMIN" && userRole !== "SUPER_ADMIN" && userRole !== "ADMIN") {
    return (
      <Card style={{ margin: "24px", textAlign: "center", background: "var(--bg-card)", border: "1px solid var(--border-color)" }}>
        <Title level={4} style={{ color: "var(--color-error)" }}>Access Denied</Title>
        <Paragraph style={{ color: "var(--text-secondary)" }}>
          You do not have administrative permissions required to manage enterprise accounts.
        </Paragraph>
      </Card>
    );
  }

  const handleOpenCreate = () => {
    if (userRole === "SYSTEM_ADMIN") {
      createForm.setFieldsValue({
        company: "",
        department: "",
        role: "SUPER_ADMIN"
      });
    } else {
      createForm.setFieldsValue({
        company: userInfo.company || "",
        department: userRole === "ADMIN" ? (userInfo.department || "") : "",
        role: "USER"
      });
    }
    setCreateFormVisible(true);
  };

  const handleOpenEdit = (user) => {
    setEditingUser(user);
    editForm.setFieldsValue({
      full_name: user.full_name,
      department: user.department,
      role: user.role,
      company: user.company || "Acme Retail",
      location: user.location || "",
      mobile_number: user.mobile_number || "",
      address: user.address || "",
      division_code: user.division_code || "",
    });
    setEditFormVisible(true);
  };

  const handleCreateSubmit = () => {
    createForm.validateFields().then((values) => {
      // Destructure to remove confirm_password and company (if not SYSTEM_ADMIN) from backend payload
      const { confirm_password, company, ...restValues } = values;
      const payload = {
        ...restValues,
        username: values.official_email,
        password: values.password,
        division_code: values.division_code || null
      };
      // Only include company payload if user is SYSTEM_ADMIN
      if (userRole === "SYSTEM_ADMIN") {
        payload.company = company;
      }
      onCreateUser(payload).then((success) => {
        if (success) {
          setCreateFormVisible(false);
          createForm.resetFields();
        }
      });
    });
  };

  const handleEditSubmit = () => {
    editForm.validateFields().then((values) => {
      onUpdateUser({ ...editingUser, ...values }).then((success) => {
        if (success) {
          setEditFormVisible(false);
          setEditingUser(null);
        }
      });
    });
  };

  // Filter local users before table render
  const filteredUsers = users.filter(user => {
    const matchesSearch = 
      !searchText ||
      user.full_name?.toLowerCase().includes(searchText.toLowerCase()) ||
      user.official_email?.toLowerCase().includes(searchText.toLowerCase()) ||
      user.employee_id?.toLowerCase().includes(searchText.toLowerCase());

    const matchesRole = filterRole === "ALL" || user.role === filterRole;
    const matchesStatus = filterStatus === "ALL" || 
      (filterStatus === "ACTIVE" ? user.is_active : !user.is_active);

    return matchesSearch && matchesRole && matchesStatus;
  });

  const columns = [
    {
      title: "Employee ID",
      dataIndex: "employee_id",
      key: "employee_id",
      render: (text) => <span style={{ fontFamily: "monospace", color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Full Name",
      dataIndex: "full_name",
      key: "full_name",
      render: (text) => <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Email",
      dataIndex: "official_email",
      key: "official_email",
      render: (text) => (
        <span style={{ color: "var(--text-muted)" }}>
          <MailOutlined style={{ marginRight: "6px" }} />
          {text}
        </span>
      )
    },
    {
      title: "Department",
      dataIndex: "department",
      key: "department",
      render: (dept) => <Tag color="geekblue" bordered={false}>{dept}</Tag>
    },
    {
      title: "Security Role",
      dataIndex: "role",
      key: "role",
      render: (role) => (
        <Tag color={role?.toUpperCase() === "ADMIN" ? "volcano" : "indigo"} bordered={false}>
          {role}
        </Tag>
      )
    },
    {
      title: "Division Access",
      dataIndex: "division_code",
      key: "division_code",
      render: (code) => (
        <Tag color={code ? "purple" : "cyan"} bordered={false}>
          {code || "All Divisions"}
        </Tag>
      )
    },
    {
      title: "Assigned Permissions",
      dataIndex: "user_roles",
      render: (roles) => {
        if (!roles?.length) return <Text type="secondary">-</Text>;
        return (
          <Space size={[4, 8]} wrap>
            {roles.map(r => <Tag key={r} color="blue" bordered={false}>{r}</Tag>)}
          </Space>
        );
      }
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive) => (
        <Badge status={isActive ? "success" : "default"} text={<span style={{ color: isActive ? "var(--text-active)" : "#6b7280" }}>{isActive ? "ACTIVE" : "INACTIVE"}</span>} />
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => {
        // Enforce hierarchy visibility rules
        if (record.role === "SUPER_ADMIN" && userRole === "ADMIN") {
          return null; // ADMIN cannot manage SUPER_ADMIN accounts
        }
        return (
          <Space size="middle">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => handleOpenEdit(record)}
              style={{ color: "var(--code-blue)" }}
            >
              Edit
            </Button>
            <Popconfirm
              title={`${record.is_active ? "Deactivate" : "Activate"} this user?`}
              onConfirm={() => onToggleStatus(record.id, record.is_active)}
              okText="Yes"
              cancelText="No"
              dropdownStyle={{ background: "var(--border-color)" }}
            >
              <Button
                type="text"
                danger={record.is_active}
                icon={record.is_active ? <LockOutlined /> : <UnlockOutlined style={{ color: "#10b981" }} />}
              >
                {record.is_active ? "Deactivate" : "Activate"}
              </Button>
            </Popconfirm>
          </Space>
        );
      }
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            User Management
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Administer enterprise accounts, update department mappings, and toggle status.
          </Text>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<UserAddOutlined />}
            onClick={handleOpenCreate}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
          >
            Add New User
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadUsers}
            style={{ background: "var(--border-color)", border: "1px solid var(--border-light)", color: "var(--text-main)" }}
          >
            Refresh List
          </Button>
        </Space>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", marginBottom: "16px" }}>
        {/* Search and Filters Bar */}
        <Row gutter={[16, 16]} style={{ marginBottom: "20px" }}>
          <Col xs={24} sm={10} md={10}>
            <Input 
              placeholder="Search by name, email or employee ID..." 
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              prefix={<SearchOutlined style={{ color: "var(--text-muted)" }} />}
              allowClear
              style={{ background: "var(--bg-card)", color: "var(--text-main)", borderColor: "var(--border-color)" }}
            />
          </Col>
          <Col xs={12} sm={7} md={7}>
            <Select 
              value={filterRole} 
              onChange={setFilterRole} 
              style={{ width: "100%" }}
              dropdownStyle={{ background: "var(--bg-card)" }}
            >
              <Option value="ALL">All Roles</Option>
              <Option value="SUPER_ADMIN">SUPER_ADMIN</Option>
              <Option value="ADMIN">ADMIN</Option>
              <Option value="ANALYST">ANALYST</Option>
              <Option value="USER">USER</Option>
            </Select>
          </Col>
          <Col xs={12} sm={7} md={7}>
            <Select 
              value={filterStatus} 
              onChange={setFilterStatus} 
              style={{ width: "100%" }}
              dropdownStyle={{ background: "var(--bg-card)" }}
            >
              <Option value="ALL">All Statuses</Option>
              <Option value="ACTIVE">ACTIVE</Option>
              <Option value="INACTIVE">INACTIVE</Option>
            </Select>
          </Col>
        </Row>

        <Table
          dataSource={filteredUsers}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 8 }}
          style={{ background: "var(--bg-card)" }}
          className="dark-table"
        />
      </Card>

      {/* CREATE USER MODAL */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Create New User</span>}
        open={createFormVisible}
        onCancel={() => setCreateFormVisible(false)}
        onOk={handleCreateSubmit}
        okText="Create User"
        okButtonProps={{ style: { backgroundColor: "#4f46e5", borderColor: "#4338ca" } }}
        destroyOnClose
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form
          form={createForm}
          layout="vertical"
        >
          <Form.Item
            name="employee_id"
            label={<span style={{ color: "var(--text-secondary)" }}>Employee ID</span>}
            rules={[{ required: true, message: "Please input Employee ID!" }]}
          >
            <Input placeholder="e.g. EMP1004" />
          </Form.Item>

          <Form.Item
            name="full_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Full Name</span>}
            rules={[{ required: true, message: "Please input Full Name!" }]}
          >
            <Input placeholder="e.g. John Doe" />
          </Form.Item>

          <Form.Item
            name="official_email"
            label={<span style={{ color: "var(--text-secondary)" }}>Official Email</span>}
            rules={[
              { required: true, message: "Please input official email!" },
              { type: "email", message: "Please enter a valid email!" }
            ]}
          >
            <Input placeholder="john.doe@company.com" />
          </Form.Item>

          <Form.Item
            name="department"
            label={<span style={{ color: "var(--text-secondary)" }}>Department</span>}
            rules={[{ required: true, message: "Please select department!" }]}
          >
            {userRole === "ADMIN" ? (
              <Input disabled />
            ) : (
              <Select placeholder="Select department">
                <Option value="Sales">Sales</Option>
                <Option value="Finance">Finance</Option>
                <Option value="HR">HR</Option>
                <Option value="Engineering">Engineering</Option>
                <Option value="Operations">Operations</Option>
                <Option value="Marketing">Marketing</Option>
                <Option value="IT">IT</Option>
              </Select>
            )}
          </Form.Item>

          <Form.Item name="role" label={<span style={{ color: "var(--text-secondary)" }}>Role</span>} rules={[{ required: true }]}>
            <Select>
              {userRole === "SYSTEM_ADMIN" && <Option value="SUPER_ADMIN">SUPER_ADMIN</Option>}
              {(userRole === "SYSTEM_ADMIN" || userRole === "SUPER_ADMIN") && <Option value="ADMIN">ADMIN</Option>}
              <Option value="ANALYST">ANALYST</Option>
              <Option value="USER">USER</Option>
            </Select>
          </Form.Item>

          {userRole === "SYSTEM_ADMIN" ? (
            <Form.Item 
              name="company" 
              label={<span style={{ color: "var(--text-secondary)" }}>Company</span>}
              rules={[{ required: true, message: "Please select a company!" }]}
            >
              <Select placeholder="Select Company">
                {companiesList.map(c => (
                  <Option key={c.company_id} value={c.company_name}>
                    {c.company_name} ({c.company_code})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          ) : (
            <Form.Item name="company" label={<span style={{ color: "var(--text-secondary)" }}>Company</span>}>
              <Input disabled />
            </Form.Item>
          )}

          <Form.Item
            name="division_code"
            label={<span style={{ color: "var(--text-secondary)" }}>Division Access</span>}
          >
            <Select placeholder="Select Allowed Division (Default: All Divisions)" allowClear>
              <Option value="">All Divisions</Option>
              <Option value="VCC">VCC</Option>
              <Option value="RR">RR</Option>
              <Option value="Finance">Finance</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="password"
            label={<span style={{ color: "var(--text-secondary)" }}>Password</span>}
            rules={[
              { required: true, message: "Please input password!" },
              { min: 8, message: "Password must be at least 8 characters!" },
              { max: 128, message: "Password must be at most 128 characters!" },
              {
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>])[A-Za-z\d!@#$%^&*(),.?":{}|<>]{8,}$/,
                message: "Password must contain at least one uppercase, one lowercase, one number, and one special character!"
              }
            ]}
          >
            <Input.Password 
              placeholder="Enter a secure password" 
              autoComplete="new-password" 
            />
          </Form.Item>

          <Form.Item
            name="confirm_password"
            label={<span style={{ color: "var(--text-secondary)" }}>Confirm Password</span>}
            dependencies={['password']}
            rules={[
              { required: true, message: "Please confirm your password!" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('Passwords do not match!'));
                },
              }),
            ]}
          >
            <Input.Password 
              placeholder="Confirm password" 
              autoComplete="new-password" 
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* EDIT USER MODAL */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Edit User Details</span>}
        open={editFormVisible}
        onCancel={() => {
          setEditFormVisible(false);
          setEditingUser(null);
        }}
        onOk={handleEditSubmit}
        okText="Save Changes"
        okButtonProps={{ style: { backgroundColor: "#4f46e5", borderColor: "#4338ca" } }}
        destroyOnClose
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="full_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Full Name</span>}
            rules={[{ required: true, message: "Please input full name!" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="department"
            label={<span style={{ color: "var(--text-secondary)" }}>Department</span>}
            rules={[{ required: true, message: "Please input department!" }]}
          >
            <Input disabled={userRole === "ADMIN"} />
          </Form.Item>

          <Form.Item name="role" label={<span style={{ color: "var(--text-secondary)" }}>Role</span>} rules={[{ required: true }]}>
            <Select>
              {userRole === "SUPER_ADMIN" && <Option value="SUPER_ADMIN">SUPER_ADMIN</Option>}
              <Option value="ADMIN">ADMIN</Option>
              <Option value="ANALYST">ANALYST</Option>
              <Option value="USER">USER</Option>
            </Select>
          </Form.Item>

          <Form.Item name="company" label={<span style={{ color: "var(--text-secondary)" }}>Company</span>}>
            <Input disabled={userRole === "ADMIN"} />
          </Form.Item>

          <Form.Item
            name="division_code"
            label={<span style={{ color: "var(--text-secondary)" }}>Division Access</span>}
          >
            <Select placeholder="Select Allowed Division (Default: All Divisions)" allowClear>
              <Option value="">All Divisions</Option>
              <Option value="VCC">VCC</Option>
              <Option value="RR">RR</Option>
              <Option value="Finance">Finance</Option>
            </Select>
          </Form.Item>

          <Form.Item name="location" label={<span style={{ color: "var(--text-secondary)" }}>Location</span>}>
            <Input placeholder="e.g. New York, London" />
          </Form.Item>

          <Form.Item name="mobile_number" label={<span style={{ color: "var(--text-secondary)" }}>Mobile Number</span>}>
            <Input placeholder="e.g. +1 555-0199" />
          </Form.Item>

          <Form.Item name="address" label={<span style={{ color: "var(--text-secondary)" }}>Address</span>}>
            <Input placeholder="Street address details" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
