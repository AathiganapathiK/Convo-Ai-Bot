import React from "react";
import { Layout, Dropdown, Avatar, Space, Button, Tag, Typography } from "antd";
import {
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  DownOutlined
} from "@ant-design/icons";

const { Header: AntHeader } = Layout;
const { Text, Title } = Typography;

// userInfo is passed in from App.js (loaded from SQL Server via /profile)
// onLogout is the Auth0-backed logout from App.js
function Header({
  openProfile,
  openUserManagement,
  openRoleManagement,
  openPlatformSettings,
  openAIProviders,
  userInfo,
  onLogout
})
{
  const menuItems = [
    {
      key: "profile",
      label: "My Profile",
      icon: <UserOutlined />,
      onClick: openProfile,
    },
    ...(userInfo?.role?.toUpperCase() === "ADMIN" || userInfo?.role?.toUpperCase() === "SUPER_ADMIN"
      ? [
          {
            key: "users",
            label: "User Management",
            icon: <SettingOutlined />,
            onClick: openUserManagement,
          },
          {
            key: "roles",
            label: "Role Management",
            icon: <SettingOutlined />,
            onClick: openRoleManagement,
          },
          {
            key: "ai-providers",
            label: "AI Providers",
            icon: <SettingOutlined />,
            onClick: openAIProviders
          },
          {
            key: "settings",
            label: "Platform Settings",
            icon: <SettingOutlined />,
            onClick: openPlatformSettings,
          },
        ]
      : []),
    {
      type: "divider",
    },
    {
      key: "logout",
      label: "Logout",
      icon: <LogoutOutlined />,
      danger: true,
      onClick: onLogout,
    },
  ];

  return (
    <AntHeader
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "0 24px",
        background: "#ffffff",
        borderBottom: "1px solid #f0f0f0",
        height: "64px",
        boxShadow: "0 1px 4px rgba(0, 21, 41, 0.08)",
        zIndex: 10,
      }}
    >
      {/* LEFT SIDE: Brand & Status */}
      <Space size="large" align="center">
        <Title level={4} style={{ margin: 0, fontWeight: 700, color: "#1e293b", letterSpacing: "-0.5px" }}>
          Conversational AI Engine
        </Title>
        {userInfo?.role && (
          <Tag color={(userInfo.role.toUpperCase() === "ADMIN" || userInfo.role.toUpperCase() === "SUPER_ADMIN") ? "volcano" : "blue"} style={{ borderRadius: "12px" }}>
            {userInfo.role.toUpperCase()}
          </Tag>
        )}
      </Space>

      {/* RIGHT SIDE: Navigation & Actions */}
      <Space size="middle">
        {(userInfo?.role?.toUpperCase() === "ADMIN" || userInfo?.role?.toUpperCase() === "SUPER_ADMIN") && (
          <Button
            type="primary"
            ghost
            onClick={openUserManagement}
            style={{ borderRadius: "6px" }}
          >
            User Panel
          </Button>
        )}
        {(userInfo?.role?.toUpperCase() === "ADMIN" || userInfo?.role?.toUpperCase() === "SUPER_ADMIN") && (  
          <Button
          type="primary"
          ghost
          onClick={openPlatformSettings}
          style={{
            borderRadius: "6px"
          }}
        >
          Platform Settings
        </Button>
        )}
        <Dropdown menu={{ items: menuItems }} trigger={["click"]} placement="bottomRight">
          <Space style={{ cursor: "pointer", padding: "4px 8px", borderRadius: "8px", transition: "all 0.2s" }} className="profile-dropdown-trigger">
            <Avatar
              style={{ backgroundColor: (userInfo?.role?.toUpperCase() === "ADMIN" || userInfo?.role?.toUpperCase() === "SUPER_ADMIN") ? "#ef4444" : "#3b82f6" }}
              icon={<UserOutlined />}
            />
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: "1.2" }}>
              <Text strong style={{ fontSize: "14px", color: "#334155" }}>
                {userInfo?.full_name || userInfo?.official_email || "User"}
              </Text>
              <Text type="secondary" style={{ fontSize: "11px" }}>
                {userInfo?.department || ""}
              </Text>
            </div>
            <DownOutlined style={{ fontSize: "10px", color: "#64748b" }} />
          </Space>
        </Dropdown>
      </Space>
    </AntHeader>
  );
}

export default Header;