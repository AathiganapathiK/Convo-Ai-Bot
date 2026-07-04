import React from "react";
import { Modal, Descriptions, Avatar, Card, Tag, Space, Divider } from "antd";
import { UserOutlined, MailOutlined, BankOutlined, IdcardOutlined, SafetyCertificateOutlined, BuildOutlined } from "@ant-design/icons";

function ProfileModal({ visible, onClose, userInfo }) {
  if (!userInfo) return null;

  return (
    <Modal
      title="User Profile Details"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={520}
      style={{ top: 80 }}
      styles={{ body: { padding: "12px 0 0 0" } }}
    >
      <Card
        bordered={false}
        style={{
          background: "var(--bg-banner)",
          marginBottom: "20px",
          textAlign: "center",
          borderRadius: "12px",
        }}
      >
        <Avatar
          size={80}
          icon={<UserOutlined />}
          style={{
            backgroundColor: userInfo.role?.toUpperCase() === "ADMIN" ? "#ef4444" : "#3b82f6",
            boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
            marginBottom: "12px",
          }}
        />
        <h3 style={{ margin: "0 0 4px 0", fontSize: "20px", color: "var(--text-banner-main)", fontWeight: 700 }}>
          {userInfo.full_name}
        </h3>
        <Space size="middle" style={{ marginTop: "4px" }}>
          <Tag color={userInfo.role?.toUpperCase() === "ADMIN" ? "volcano" : "blue"} style={{ borderRadius: "10px" }}>
            {userInfo.role}
          </Tag>
          <Tag color="purple" style={{ borderRadius: "10px" }}>
            {userInfo.department}
          </Tag>
        </Space>
      </Card>

      <div style={{ padding: "0 10px" }}>
        <Descriptions column={1} bordered size="middle" labelStyle={{ width: "160px", fontWeight: 600, color: "var(--text-secondary)" }}>
          <Descriptions.Item label={<span><IdcardOutlined style={{ marginRight: 8, color: "#6366f1" }} />Employee ID</span>}>
            {userInfo.employee_id || "N/A"}
          </Descriptions.Item>
          <Descriptions.Item label={<span><MailOutlined style={{ marginRight: 8, color: "#6366f1" }} />Official Email</span>}>
            {userInfo.official_email || "N/A"}
          </Descriptions.Item>
          <Descriptions.Item label={<span><BankOutlined style={{ marginRight: 8, color: "#6366f1" }} />Department</span>}>
            {userInfo.department || "N/A"}
          </Descriptions.Item>
          <Descriptions.Item label={<span><SafetyCertificateOutlined style={{ marginRight: 8, color: "#6366f1" }} />System Role</span>}>
            <span style={{ fontWeight: 600 }}>{userInfo.role || "N/A"}</span>
          </Descriptions.Item>
          <Descriptions.Item label={<span><BuildOutlined style={{ marginRight: 8, color: "#6366f1" }} />Company</span>}>
            {userInfo.company || "N/A"}
          </Descriptions.Item>
        </Descriptions>
      </div>
      <Divider style={{ margin: "20px 0 10px 0" }} />
    </Modal>
  );
}

export default ProfileModal;
