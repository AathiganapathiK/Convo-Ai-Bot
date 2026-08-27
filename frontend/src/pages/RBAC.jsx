import React, { useState, useEffect } from "react";
import {
  Table, Card, Button, Tag, Space, Typography,
  Input, Select, Row, Col, Tabs, Tooltip, Popover, Checkbox, Switch
} from "antd";
import { message } from "../utils/message";
import {
  SearchOutlined, SafetyCertificateOutlined, UserOutlined,
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, TeamOutlined,
  GlobalOutlined, AppstoreOutlined, NodeIndexOutlined, ClusterOutlined
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

// Standard Enterprise Domain Data Scopes
const SCOPE_OPTIONS = {
  REGION: [
    "Tamil Nadu", "Karnataka", "Kerala", "Andhra Pradesh",
    "Telangana", "North Region", "West Region", "East Region", "Overseas"
  ],
  PRODUCT: [
    "Sales", "Finance", "HR", "Engineering", "Operations",
    "Marketing", "IT", "Customer Care", "Dispatch", "Retail"
  ],
  CHANNEL: [
    "Showroom", "Franchise", "Marketing", "Direct", "Online", "Wholesale"
  ],
  DIVISION: [
    "ACC", "AKG", "ATC", "BandB", "RHL", "RR", "RRF", "TARA", "VGS", "VT",
    "Sales", "Manufacturing", "Finance", "HR", "IT"
  ]
};

export default function RBAC({ API, token, userInfo }) {
  const [activeTab, setActiveTab] = useState("users"); // "users" | "roles"
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState(null);

  // Dynamic Scope Options from Backend API
  const [scopeOptions, setScopeOptions] = useState({
    REGION: [],
    PRODUCT: [],
    CHANNEL: [],
    DIVISION: []
  });

  // Data states
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [roleMatrixMap, setRoleMatrixMap] = useState({}); // role_id -> matrix
  const [userMatrixMap, setUserMatrixMap] = useState({}); // employee_id -> matrix

  // Search & Filter states
  const [searchText, setSearchText] = useState("");
  const [filterRole, setFilterRole] = useState("ALL");
  const [filterDepartment, setFilterDepartment] = useState("ALL");
  const [popoverSearchText, setPopoverSearchText] = useState({});

  // Fetch initial data & master scope values dynamically
  useEffect(() => {
    if (token) {
      loadInitialData();
      fetchMasterScopes();
    }
  }, [token]);

  const fetchMasterScopes = async () => {
    try {
      const res = await fetch(`${API}/access-control/scopes/master`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setScopeOptions(data);
      }
    } catch (e) {
      console.error("Failed to load dynamic master scopes", e);
    }
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // 1. Fetch Users
      const uRes = await fetch(`${API}/admin/users`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (uRes.ok) {
        const uData = await uRes.json();
        setUsers(uData);
        uData.forEach(u => {
          if (u.employee_id) {
            fetchUserMatrix(u.employee_id);
          }
        });
      }

      // 2. Fetch Roles
      const rRes = await fetch(`${API}/roles`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (rRes.ok) {
        const rData = await rRes.json();
        setRoles(rData);
        rData.forEach(r => {
          fetchRoleMatrix(r.id);
        });
      }
    } catch (err) {
      console.error("Failed to load RBAC data", err);
      message.error("Failed to load access control data");
    } finally {
      setLoading(false);
    }
  };

  const fetchRoleMatrix = async (roleId) => {
    try {
      const res = await fetch(`${API}/roles/${roleId}/matrix`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setRoleMatrixMap(prev => ({ ...prev, [roleId]: data }));
      }
    } catch (e) {
      console.error(`Failed to load role matrix for role ${roleId}`, e);
    }
  };

  const fetchUserMatrix = async (employeeId) => {
    try {
      const res = await fetch(`${API}/admin/users/${employeeId}/matrix`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUserMatrixMap(prev => ({ ...prev, [employeeId]: data }));
      }
    } catch (e) {
      console.error(`Failed to load user matrix for user ${employeeId}`, e);
    }
  };

  // Direct Inline Save User Permissions & Data Scope (with Rollback on Failure)
  const saveUserMatrixInline = async (employeeId, updatedChatOverrides, updatedDataScope) => {
    const key = `user_${employeeId}`;
    setSavingKey(key);
    const previousMatrix = userMatrixMap[employeeId] || {};

    const payload = {
      chat_overrides: updatedChatOverrides !== undefined ? updatedChatOverrides : (previousMatrix.chat_overrides || {}),
      data_scope: updatedDataScope !== undefined ? updatedDataScope : (previousMatrix.data_scope || {})
    };

    setUserMatrixMap(prev => ({
      ...prev,
      [employeeId]: {
        ...(prev[employeeId] || {}),
        chat_overrides: payload.chat_overrides,
        data_scope: payload.data_scope
      }
    }));

    try {
      const res = await fetch(`${API}/admin/users/${employeeId}/matrix`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        message.success(`User access updated successfully`);
      } else {
        const err = await res.json();
        setUserMatrixMap(prev => ({ ...prev, [employeeId]: previousMatrix }));
        message.error(err.detail || "Failed to update user matrix");
      }
    } catch (err) {
      console.error("Save user matrix error:", err);
      setUserMatrixMap(prev => ({ ...prev, [employeeId]: previousMatrix }));
      message.error("Network error updating user access");
    } finally {
      setSavingKey(null);
    }
  };

  // Direct Inline Save Role Permissions & Data Scope (with Rollback on Failure)
  const saveRoleMatrixInline = async (roleId, updatedChatAccess, updatedDataScope) => {
    const key = `role_${roleId}`;
    setSavingKey(key);
    const previousMatrix = roleMatrixMap[roleId] || {};

    const payload = {
      page_access: previousMatrix.page_access || {},
      chat_access: updatedChatAccess !== undefined ? updatedChatAccess : (previousMatrix.chat_access || {}),
      data_scope: updatedDataScope !== undefined ? updatedDataScope : (previousMatrix.data_scope || {})
    };

    setRoleMatrixMap(prev => ({
      ...prev,
      [roleId]: {
        ...(prev[roleId] || {}),
        chat_access: payload.chat_access,
        data_scope: payload.data_scope
      }
    }));

    try {
      const res = await fetch(`${API}/roles/${roleId}/matrix`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        message.success("Role permissions updated successfully");
      } else {
        const err = await res.json();
        setRoleMatrixMap(prev => ({ ...prev, [roleId]: previousMatrix }));
        message.error(err.detail || "Failed to update role matrix");
      }
    } catch (err) {
      console.error("Save role matrix error:", err);
      setRoleMatrixMap(prev => ({ ...prev, [roleId]: previousMatrix }));
      message.error("Network error updating role access");
    } finally {
      setSavingKey(null);
    }
  };

  // Filter Users
  const filteredUsers = users.filter(u => {
    const matchesSearch =
      u.full_name?.toLowerCase().includes(searchText.toLowerCase()) ||
      u.official_email?.toLowerCase().includes(searchText.toLowerCase()) ||
      u.employee_id?.toLowerCase().includes(searchText.toLowerCase());
    const matchesRole = filterRole === "ALL" || u.role === filterRole;
    const matchesDept = filterDepartment === "ALL" || u.department === filterDepartment;
    return matchesSearch && matchesRole && matchesDept;
  });

  // Filter Roles
  const filteredRoles = roles.filter(r => {
    return (
      r.role_name?.toLowerCase().includes(searchText.toLowerCase()) ||
      r.description?.toLowerCase().includes(searchText.toLowerCase())
    );
  });

  // Avatar Initials & Color Helpers
  const getInitials = (name) => {
    if (!name) return "U";
    const parts = name.trim().split(" ");
    if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
    return name.substring(0, 2).toUpperCase();
  };

  const avatarColors = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6"];
  const getAvatarColor = (str) => {
    let hash = 0;
    for (let i = 0; i < (str || "").length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return avatarColors[Math.abs(hash) % avatarColors.length];
  };

  // Render Inline Scope Selector Component (Responsive Fit & Global Blue Accent)
  const renderInlineScopeSelector = (dimKey, currentValues, onSave, labelIcon, labelName) => {
    const rawOptions = (scopeOptions[dimKey] && scopeOptions[dimKey].length > 0) ? scopeOptions[dimKey] : (SCOPE_OPTIONS[dimKey] || []);
    const filterQuery = (popoverSearchText[dimKey] || "").toLowerCase();
    const options = rawOptions.filter(opt => opt.toLowerCase().includes(filterQuery));
    const selectedList = currentValues || [];
    const isAll = rawOptions.length > 0 && rawOptions.every(opt => selectedList.includes(opt));
    const isNone = selectedList.length === 0;

    const handleToggleVal = (val) => {
      let nextList = [...selectedList];
      if (nextList.includes(val)) {
        nextList = nextList.filter(v => v !== val);
      } else {
        nextList.push(val);
      }
      onSave(nextList);
    };

    const handleSelectAll = () => {
      onSave([...rawOptions]);
    };

    const handleClearAll = () => {
      onSave([]);
    };

    const popoverContent = (
      <div style={{ width: "260px", padding: "6px 4px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", borderBottom: "1px solid var(--border-color)", paddingBottom: "6px" }}>
          <Text bold style={{ fontSize: "13px", color: "var(--text-main)" }}>
            {labelName} Scopes ({selectedList.length}/{rawOptions.length})
          </Text>
          <Space size="small">
            <Button size="small" type="text" onClick={handleSelectAll} style={{ fontSize: "12px", color: "var(--color-accent-blue)", padding: "0 4px", fontWeight: 600 }}>Select All</Button>
            <Button size="small" type="text" onClick={handleClearAll} style={{ fontSize: "12px", color: "#ef4444", padding: "0 4px", fontWeight: 600 }}>Clear</Button>
          </Space>
        </div>

        <Input
          placeholder={`Search ${labelName.toLowerCase()}s...`}
          size="small"
          prefix={<SearchOutlined style={{ color: "var(--text-muted)", fontSize: "12px" }} />}
          value={popoverSearchText[dimKey] || ""}
          onChange={e => setPopoverSearchText(prev => ({ ...prev, [dimKey]: e.target.value }))}
          style={{ marginBottom: "8px", borderRadius: "6px" }}
          allowClear
        />

        <div style={{ maxHeight: "190px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "4px" }}>
          {options.length === 0 ? (
            <Text type="secondary" style={{ fontSize: "12px", padding: "8px", textAlign: "center" }}>No options found</Text>
          ) : (
            options.map(opt => {
              const checked = selectedList.includes(opt);
              return (
                <div
                  key={opt}
                  onClick={() => handleToggleVal(opt)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "5px 8px",
                    borderRadius: "6px",
                    cursor: "pointer",
                    backgroundColor: checked ? "var(--color-accent-blue-bg)" : "transparent",
                    transition: "all 0.15s ease"
                  }}
                >
                  <Text style={{ fontSize: "13px", color: checked ? "var(--color-accent-blue)" : "var(--text-main)", fontWeight: checked ? 600 : 400 }}>
                    {opt}
                  </Text>
                  <Checkbox checked={checked} onChange={() => {}} />
                </div>
              );
            })
          )}
        </div>
      </div>
    );

    return (
      <Popover content={popoverContent} trigger="click" placement="bottomLeft">
        <div
          style={{
            cursor: "pointer",
            padding: "4px 6px",
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
            backgroundColor: "var(--bg-card)",
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            width: "100%",
            maxWidth: "115px",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            boxShadow: "0 1px 2px rgba(0,0,0,0.02)"
          }}
        >
          {labelIcon}
          {isAll ? (
            <Tag color="purple" style={{ margin: 0, borderRadius: "4px", fontSize: "11px", fontWeight: 600 }}>All</Tag>
          ) : isNone ? (
            <Text style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)" }}>No Access</Text>
          ) : (
            <Text bold style={{ fontSize: "12px", color: "var(--color-accent-blue)" }}>
              {selectedList.length} Selected
            </Text>
          )}
        </div>
      </Popover>
    );
  };

  // Render Inline Chat Perm Switch for Users (Allow / Deny Switch)
  const renderUserChatPermSwitch = (user, permKey) => {
    const uMatrix = userMatrixMap[user.employee_id] || {};
    const chatOv = uMatrix.chat_overrides || {};
    const rawVal = chatOv[permKey];

    const userRoleObj = roles.find(r => r.role_name === user.role);
    const roleMatrix = userRoleObj ? roleMatrixMap[userRoleObj.id] : null;
    const defaultRoleChat = roleMatrix?.chat_access || { a: true, h: true, d: false };
    const roleAllowed = !!defaultRoleChat[permKey];

    let isAllowed = roleAllowed;
    if (rawVal === "denied") isAllowed = false;
    if (rawVal === "allowed") isAllowed = true;

    const handleToggle = (checked) => {
      const nextVal = checked ? "allowed" : "denied";
      const updatedOv = { ...chatOv, [permKey]: nextVal };
      saveUserMatrixInline(user.employee_id, updatedOv, undefined);
    };

    return (
      <Space size="small" style={{ width: "100%" }}>
        <Switch
          size="small"
          checked={isAllowed}
          onChange={handleToggle}
          style={{ backgroundColor: isAllowed ? "var(--color-allow)" : "#94a3b8" }}
        />
        <Tag color={isAllowed ? "success" : "default"} style={{ margin: 0, borderRadius: "5px", fontSize: "11px", fontWeight: 600, padding: "1px 6px" }}>
          {isAllowed ? "Allow" : "Deny"}
        </Tag>
      </Space>
    );
  };

  // Render Inline Chat Perm Switch for Roles (Allow / Deny Switch)
  const renderRoleChatPermSwitch = (roleObj, permKey) => {
    const matrix = roleMatrixMap[roleObj.id] || {};
    const chatAcc = matrix.chat_access || { a: true, h: true, d: false };
    const isAllowed = roleObj.role_name === "SUPER_ADMIN" ? true : !!chatAcc[permKey];

    const handleToggle = (checked) => {
      if (roleObj.role_name === "SUPER_ADMIN") return;
      const updatedAcc = { ...chatAcc, [permKey]: checked };
      saveRoleMatrixInline(roleObj.id, updatedAcc, undefined);
    };

    return (
      <Space size="small" style={{ width: "100%" }}>
        <Switch
          size="small"
          checked={isAllowed}
          disabled={roleObj.role_name === "SUPER_ADMIN"}
          onChange={handleToggle}
          style={{ backgroundColor: isAllowed ? "var(--color-allow)" : "#94a3b8" }}
        />
        <Tag color={isAllowed ? "success" : "default"} style={{ margin: 0, borderRadius: "5px", fontSize: "11px", fontWeight: 600, padding: "1px 6px" }}>
          {isAllowed ? "Allow" : "Deny"}
        </Tag>
      </Space>
    );
  };

  // Table Columns for By Users Matrix (Responsive Proportional Widths - 100% Fit)
  const userColumns = [
    {
      title: "USER IDENTITY",
      key: "user",
      width: "20%",
      render: (_, record) => (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", width: "100%", overflow: "hidden" }}>
          <div
            style={{
              width: 34,
              height: 34,
              minWidth: 34,
              borderRadius: "50%",
              backgroundColor: getAvatarColor(record.full_name),
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: "13px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)"
            }}
          >
            {getInitials(record.full_name)}
          </div>
          <div style={{ minWidth: 0, flex: 1, overflow: "hidden" }}>
            <Tooltip title={record.full_name} placement="top">
              <Text bold style={{ color: "var(--text-main)", fontSize: "14px", display: "block", lineHeight: "1.2", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {record.full_name}
              </Text>
            </Tooltip>
            <Tooltip title={record.official_email || record.employee_id} placement="bottom">
              <Text type="secondary" style={{ fontSize: "12.5px", color: "var(--text-muted)", display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {record.official_email || record.employee_id}
              </Text>
            </Tooltip>
          </div>
        </div>
      )
    },
    {
      title: "ROLE",
      dataIndex: "role",
      key: "role",
      width: "10%",
      render: (roleName) => (
        <Tag
          color={roleName === "SUPER_ADMIN" ? "purple" : roleName === "ADMIN" ? "volcano" : "blue"}
          variant="filled"
          style={{ borderRadius: "6px", fontWeight: 600, padding: "2px 6px", fontSize: "11px" }}
        >
          {roleName === "SUPER_ADMIN" ? <SafetyCertificateOutlined /> : <UserOutlined />} {roleName}
        </Tag>
      )
    },
    {
      title: "ASK",
      key: "ask_perm",
      width: "8%",
      render: (_, record) => renderUserChatPermSwitch(record, "a")
    },
    {
      title: "HISTORY",
      key: "history_perm",
      width: "8%",
      render: (_, record) => renderUserChatPermSwitch(record, "h")
    },
    {
      title: "DELETE",
      key: "delete_perm",
      width: "8%",
      render: (_, record) => renderUserChatPermSwitch(record, "d")
    },
    {
      title: "REGION",
      key: "region_scope",
      width: "11.5%",
      render: (_, record) => {
        const uMatrix = userMatrixMap[record.employee_id] || {};
        const currentScopes = uMatrix.data_scope?.REGION || [];
        return renderInlineScopeSelector(
          "REGION",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(uMatrix.data_scope || {}), REGION: newList };
            saveUserMatrixInline(record.employee_id, undefined, updatedDs);
          },
          <GlobalOutlined style={{ color: "#6366f1", fontSize: "12px" }} />,
          "Region"
        );
      }
    },
    {
      title: "DEPT",
      key: "product_scope",
      width: "11.5%",
      render: (_, record) => {
        const uMatrix = userMatrixMap[record.employee_id] || {};
        const currentScopes = uMatrix.data_scope?.PRODUCT || [];
        return renderInlineScopeSelector(
          "PRODUCT",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(uMatrix.data_scope || {}), PRODUCT: newList };
            saveUserMatrixInline(record.employee_id, undefined, updatedDs);
          },
          <AppstoreOutlined style={{ color: "#06b6d4", fontSize: "12px" }} />,
          "Department"
        );
      }
    },
    {
      title: "CHANNEL",
      key: "channel_scope",
      width: "11.5%",
      render: (_, record) => {
        const uMatrix = userMatrixMap[record.employee_id] || {};
        const currentScopes = uMatrix.data_scope?.CHANNEL || [];
        return renderInlineScopeSelector(
          "CHANNEL",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(uMatrix.data_scope || {}), CHANNEL: newList };
            saveUserMatrixInline(record.employee_id, undefined, updatedDs);
          },
          <NodeIndexOutlined style={{ color: "#f59e0b", fontSize: "12px" }} />,
          "Channel"
        );
      }
    },
    {
      title: "DIVISION",
      key: "division_scope",
      width: "11.5%",
      render: (_, record) => {
        const uMatrix = userMatrixMap[record.employee_id] || {};
        const currentScopes = uMatrix.data_scope?.DIVISION || [];
        return renderInlineScopeSelector(
          "DIVISION",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(uMatrix.data_scope || {}), DIVISION: newList };
            saveUserMatrixInline(record.employee_id, undefined, updatedDs);
          },
          <ClusterOutlined style={{ color: "#10b981", fontSize: "12px" }} />,
          "Division"
        );
      }
    }
  ];

  // Table Columns for By Roles Matrix
  const roleColumns = [
    {
      title: "ROLE IDENTITY",
      key: "role_name",
      width: "20%",
      render: (_, record) => (
        <div style={{ minWidth: 0, overflow: "hidden" }}>
          <Text bold style={{ color: "var(--text-main)", fontSize: "14px", display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {record.role_name}
          </Text>
          <Text type="secondary" style={{ display: "block", fontSize: "12.5px", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {record.description || "System security role"}
          </Text>
        </div>
      )
    },
    {
      title: "ASSIGNED USERS",
      key: "users_count",
      width: "10%",
      render: (_, record) => {
        const count = users.filter(u => u.role === record.role_name).length;
        return (
          <Tag color="geekblue" style={{ borderRadius: "6px", fontWeight: 600, fontSize: "11px" }}>
            <TeamOutlined /> {count} {count === 1 ? "User" : "Users"}
          </Tag>
        );
      }
    },
    {
      title: "ASK",
      key: "ask_perm",
      width: "8%",
      render: (_, record) => renderRoleChatPermSwitch(record, "a")
    },
    {
      title: "HISTORY",
      key: "history_perm",
      width: "8%",
      render: (_, record) => renderRoleChatPermSwitch(record, "h")
    },
    {
      title: "DELETE",
      key: "delete_perm",
      width: "8%",
      render: (_, record) => renderRoleChatPermSwitch(record, "d")
    },
    {
      title: "REGION",
      key: "region_scope",
      width: "11.5%",
      render: (_, record) => {
        const rMatrix = roleMatrixMap[record.id] || {};
        const currentScopes = rMatrix.data_scope?.REGION || [];
        return renderInlineScopeSelector(
          "REGION",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(rMatrix.data_scope || {}), REGION: newList };
            saveRoleMatrixInline(record.id, undefined, updatedDs);
          },
          <GlobalOutlined style={{ color: "#6366f1", fontSize: "12px" }} />,
          "Region"
        );
      }
    },
    {
      title: "DEPT",
      key: "product_scope",
      width: "11.5%",
      render: (_, record) => {
        const rMatrix = roleMatrixMap[record.id] || {};
        const currentScopes = rMatrix.data_scope?.PRODUCT || [];
        return renderInlineScopeSelector(
          "PRODUCT",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(rMatrix.data_scope || {}), PRODUCT: newList };
            saveRoleMatrixInline(record.id, undefined, updatedDs);
          },
          <AppstoreOutlined style={{ color: "#06b6d4", fontSize: "12px" }} />,
          "Department"
        );
      }
    },
    {
      title: "CHANNEL",
      key: "channel_scope",
      width: "11.5%",
      render: (_, record) => {
        const rMatrix = roleMatrixMap[record.id] || {};
        const currentScopes = rMatrix.data_scope?.CHANNEL || [];
        return renderInlineScopeSelector(
          "CHANNEL",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(rMatrix.data_scope || {}), CHANNEL: newList };
            saveRoleMatrixInline(record.id, undefined, updatedDs);
          },
          <NodeIndexOutlined style={{ color: "#f59e0b", fontSize: "12px" }} />,
          "Channel"
        );
      }
    },
    {
      title: "DIVISION",
      key: "division_scope",
      width: "11.5%",
      render: (_, record) => {
        const rMatrix = roleMatrixMap[record.id] || {};
        const currentScopes = rMatrix.data_scope?.DIVISION || [];
        return renderInlineScopeSelector(
          "DIVISION",
          currentScopes,
          (newList) => {
            const updatedDs = { ...(rMatrix.data_scope || {}), DIVISION: newList };
            saveRoleMatrixInline(record.id, undefined, updatedDs);
          },
          <ClusterOutlined style={{ color: "#10b981", fontSize: "12px" }} />,
          "Division"
        );
      }
    }
  ];

  const totalUsers = users.length;
  const totalRoles = roles.length;
  const usersWithCustomAccess = users.filter(u => {
    const uMatrix = userMatrixMap[u.employee_id];
    const uChatOv = uMatrix?.chat_overrides || {};
    return !!(uChatOv.a || uChatOv.h || uChatOv.d);
  }).length;

  return (
    <div style={{ padding: "4px", overflowX: "hidden" }}>
      <style>{`
        .rbac-matrix-table {
          width: 100% !important;
          max-width: 100% !important;
          table-layout: fixed !important;
        }
        .rbac-matrix-table .ant-table-container {
          width: 100% !important;
          overflow-x: hidden !important;
        }
        .rbac-matrix-table .ant-table-content {
          width: 100% !important;
          overflow-x: hidden !important;
        }
        .rbac-matrix-table .ant-table-cell {
          padding: 8px 4px !important;
          vertical-align: middle !important;
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
          font-size: 13.5px !important;
        }
        .rbac-matrix-table .ant-table-row {
          height: 56px !important;
        }
        .rbac-matrix-table th {
          line-height: 1.2 !important;
          font-size: 12px !important;
          font-weight: 700 !important;
          letter-spacing: 0.5px !important;
          color: var(--text-main) !important;
          padding: 8px 4px !important;
        }
      `}</style>

      {/* 1. Header Hero Banner */}
      <div
        style={{
          background: "linear-gradient(135deg, #3730a3 0%, #4f46e5 60%, #6366f1 100%)",
          borderRadius: "14px",
          padding: "18px 24px",
          color: "#ffffff",
          marginBottom: "16px",
          boxShadow: "0 10px 20px -5px rgba(79, 70, 229, 0.25)"
        }}
      >
        <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "1px", opacity: 0.85, fontWeight: 600, marginBottom: "2px" }}>
          Access Control &nbsp;›&nbsp; RBAC Matrix
        </div>
        <Row justify="space-between" align="middle">
          <Col xs={24} md={16}>
            <Title level={3} style={{ color: "#ffffff", margin: 0, fontWeight: 800, letterSpacing: "-0.5px" }}>
              <SafetyCertificateOutlined style={{ marginRight: "8px" }} />
              Access Control
            </Title>
            <Paragraph style={{ color: "rgba(255,255,255,0.9)", margin: "4px 0 0 0", fontSize: "13px" }}>
              Manage chatbot permissions and data access scopes for users and roles.
            </Paragraph>
          </Col>
          <Col xs={24} md={8} style={{ textAlign: "right" }}>
            <Space wrap size="middle">
              <div style={{ backgroundColor: "rgba(255,255,255,0.15)", borderRadius: "6px", padding: "4px 10px", fontSize: "12px", color: "#ffffff" }}>
                <Space size="small">
                  <span><CheckCircleOutlined style={{ color: "var(--color-allow)" }} /> Allowed</span>
                  <span><CloseCircleOutlined style={{ color: "#f87171" }} /> Denied</span>
                </Space>
              </div>
              <Button
                icon={<ReloadOutlined />}
                onClick={loadInitialData}
                loading={loading}
                size="small"
                style={{
                  backgroundColor: "rgba(255,255,255,0.2)",
                  borderColor: "rgba(255,255,255,0.3)",
                  color: "#ffffff",
                  borderRadius: "6px",
                  fontWeight: 600
                }}
              >
                Refresh
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

      {/* 2. Top Metric Cards Row */}
      <Row gutter={[12, 12]} style={{ marginBottom: "16px" }}>
        <Col xs={12} sm={6}>
          <Card bordered={false} style={{ borderRadius: "10px", background: "var(--bg-card)", border: "1px solid var(--border-color)", padding: "10px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ width: "38px", height: "38px", borderRadius: "8px", backgroundColor: "rgba(99, 102, 241, 0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <UserOutlined style={{ fontSize: "18px", color: "#6366f1" }} />
              </div>
              <div>
                <Title level={4} style={{ margin: 0, color: "var(--text-main)", fontWeight: 700 }}>
                  {totalUsers}
                </Title>
                <Text style={{ color: "var(--text-muted)", fontSize: "12px" }}>System Users</Text>
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card bordered={false} style={{ borderRadius: "10px", background: "var(--bg-card)", border: "1px solid var(--border-color)", padding: "10px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ width: "38px", height: "38px", borderRadius: "8px", backgroundColor: "var(--color-allow-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <TeamOutlined style={{ fontSize: "18px", color: "var(--color-allow)" }} />
              </div>
              <div>
                <Title level={4} style={{ margin: 0, color: "var(--text-main)", fontWeight: 700 }}>
                  {totalRoles}
                </Title>
                <Text style={{ color: "var(--text-muted)", fontSize: "12px" }}>Active Roles</Text>
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card bordered={false} style={{ borderRadius: "10px", background: "var(--bg-card)", border: "1px solid var(--border-color)", padding: "10px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ width: "38px", height: "38px", borderRadius: "8px", backgroundColor: "rgba(168, 85, 247, 0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <SafetyCertificateOutlined style={{ fontSize: "18px", color: "#a855f7" }} />
              </div>
              <div>
                <Title level={4} style={{ margin: 0, color: "var(--text-main)", fontWeight: 700 }}>
                  {usersWithCustomAccess}
                </Title>
                <Text style={{ color: "var(--text-muted)", fontSize: "12px" }}>User Overrides</Text>
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={12} sm={6}>
          <Card bordered={false} style={{ borderRadius: "10px", background: "var(--bg-card)", border: "1px solid var(--border-color)", padding: "10px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ width: "38px", height: "38px", borderRadius: "8px", backgroundColor: "var(--color-accent-blue-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <GlobalOutlined style={{ fontSize: "18px", color: "var(--color-accent-blue)" }} />
              </div>
              <div>
                <Title level={4} style={{ margin: 0, color: "var(--text-main)", fontWeight: 700 }}>
                  4D Scopes
                </Title>
                <Text style={{ color: "var(--text-muted)", fontSize: "12px" }}>Region, Dept, Chan, Div</Text>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 3. Main Container Card with Mode Switcher & Filters */}
      <Card bordered={false} style={{ borderRadius: "14px", background: "var(--bg-card)", border: "1px solid var(--border-color)", boxShadow: "0 4px 12px rgba(0,0,0,0.03)" }}>
        {/* Mode Tabs */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "14px" }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            type="card"
            style={{ marginBottom: 0 }}
            items={[
              {
                key: "users",
                label: (
                  <span style={{ padding: "0 12px", fontWeight: 600, fontSize: "13px" }}>
                    <UserOutlined /> By Users
                  </span>
                )
              },
              {
                key: "roles",
                label: (
                  <span style={{ padding: "0 12px", fontWeight: 600, fontSize: "13px" }}>
                    <TeamOutlined /> By Roles
                  </span>
                )
              }
            ]}
          />

          {/* Quick Info Badge */}
          <Space wrap size="small">
            <Tag color="blue" style={{ borderRadius: "8px", fontWeight: 500, padding: "2px 10px", fontSize: "12px" }}>
              ✓ Inline Auto-Save Active
            </Tag>
          </Space>
        </div>

        {/* Search & Filter Bar */}
        <Row gutter={[12, 12]} style={{ marginBottom: "14px" }}>
          <Col xs={24} sm={12} md={10}>
            <Input
              placeholder={activeTab === "users" ? "Search users by name, email or employee ID..." : "Search roles by name or description..."}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              prefix={<SearchOutlined style={{ color: "var(--text-muted)" }} />}
              allowClear
              size="middle"
              style={{ borderRadius: "8px", fontSize: "14px" }}
            />
          </Col>

          {activeTab === "users" && (
            <>
              <Col xs={12} sm={6} md={7}>
                <Select
                  value={filterRole}
                  onChange={setFilterRole}
                  style={{ width: "100%" }}
                  size="middle"
                  placeholder="Filter by Role"
                  dropdownStyle={{ background: "var(--bg-card)" }}
                >
                  <Option value="ALL">All Roles</Option>
                  {roles.map(r => (
                    <Option key={r.id} value={r.role_name}>{r.role_name}</Option>
                  ))}
                </Select>
              </Col>

              <Col xs={12} sm={6} md={7}>
                <Select
                  value={filterDepartment}
                  onChange={setFilterDepartment}
                  style={{ width: "100%" }}
                  size="middle"
                  placeholder="Filter by Department"
                  dropdownStyle={{ background: "var(--bg-card)" }}
                >
                  <Option value="ALL">All Departments</Option>
                  <Option value="Sales">Sales</Option>
                  <Option value="Finance">Finance</Option>
                  <Option value="HR">HR</Option>
                  <Option value="Engineering">Engineering</Option>
                  <Option value="Operations">Operations</Option>
                  <Option value="IT">IT</Option>
                </Select>
              </Col>
            </>
          )}
        </Row>

        {/* Inline Permission Matrix Tables (100% Fit Responsive Layout - No Horizontal Scroll) */}
        {activeTab === "users" ? (
          <Table
            dataSource={filteredUsers}
            columns={userColumns}
            rowKey="id"
            loading={loading}
            pagination={{ pageSize: 10 }}
            className="dark-table rbac-matrix-table"
          />
        ) : (
          <Table
            dataSource={filteredRoles}
            columns={roleColumns}
            rowKey="id"
            loading={loading}
            pagination={false}
            className="dark-table rbac-matrix-table"
          />
        )}
      </Card>
    </div>
  );
}
