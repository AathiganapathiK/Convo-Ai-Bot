import React, { useEffect, useState } from "react";
import {
  Modal,
  Table,
  Button,
  Form,
  Input,
  Space,
  Tag,
  message,
  Tabs,
} from "antd";

import {
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import {
  getProviders,
  createProvider,
  getModels,
} from "../services/providerService";

function AIProviderManagementModal({
  visible,
  onClose,
  token,
}) {
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);

  const [loadingProviders, setLoadingProviders] =
    useState(false);

  const [loadingModels, setLoadingModels] =
    useState(false);

  const [
    createProviderVisible,
    setCreateProviderVisible,
  ] = useState(false);

  const [form] = Form.useForm();

  useEffect(() => {
    if (visible) {
      loadProviders();
      loadModels();
    }
  }, [visible]);

  const loadProviders = async () => {
    try {
      setLoadingProviders(true);

      const data = await getProviders(token);

      setProviders(data || []);
    } catch {
      message.error("Failed to load providers");
    }

    setLoadingProviders(false);
  };

  const loadModels = async () => {
    try {
      setLoadingModels(true);

      const data = await getModels(token);

      setModels(data || []);
    } catch {
      message.error("Failed to load models");
    }

    setLoadingModels(false);
  };

  const handleCreateProvider = async () => {
    try {
      const values =
        await form.validateFields();

      await createProvider(
        token,
        values
      );

      message.success(
        "Provider created successfully"
      );

      form.resetFields();

      setCreateProviderVisible(false);

      loadProviders();
    } catch {
      message.error(
        "Failed to create provider"
      );
    }
  };

  const providerColumns = [
    {
      title: "Provider Name",
      dataIndex: "provider_name",
      key: "provider_name",
    },
    {
      title: "Provider Type",
      dataIndex: "provider_type",
      key: "provider_type",
      render: (value) => (
        <Tag color="blue">{value}</Tag>
      ),
    },
    {
      title: "Base URL",
      dataIndex: "base_url",
      key: "base_url",
      render: (value) =>
        value || "-",
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (value) =>
        value ? (
          <Tag color="green">
            ACTIVE
          </Tag>
        ) : (
          <Tag color="red">
            INACTIVE
          </Tag>
        ),
    },
    {
      title: "Created At",
      dataIndex: "created_at",
      key: "created_at",
    },
  ];

  const modelColumns = [
    {
      title: "Model Name",
      dataIndex: "model_name",
      key: "model_name",
    },
    {
      title: "Purpose",
      dataIndex: "purpose",
      key: "purpose",
      render: (value) => (
        <Tag color="purple">
          {value}
        </Tag>
      ),
    },
    {
      title: "Default",
      dataIndex: "is_default",
      key: "is_default",
      render: (value) =>
        value ? (
          <Tag color="green">
            YES
          </Tag>
        ) : (
          <Tag>NO</Tag>
        ),
    },
    {
      title: "Active",
      dataIndex: "is_active",
      key: "is_active",
      render: (value) =>
        value ? (
          <Tag color="green">
            ACTIVE
          </Tag>
        ) : (
          <Tag color="red">
            INACTIVE
          </Tag>
        ),
    },
  ];

  return (
    <>
      <Modal
        title="AI Provider Management"
        open={visible}
        onCancel={onClose}
        footer={null}
        width={1100}
      >
        <div
          style={{
            marginBottom: 16,
            display: "flex",
            justifyContent:
              "space-between",
          }}
        >
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() =>
                setCreateProviderVisible(
                  true
                )
              }
            >
              Add Provider
            </Button>

            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                loadProviders();
                loadModels();
              }}
            >
              Refresh
            </Button>
          </Space>
        </div>

        <Tabs
          items={[
            {
              key: "providers",
              label: "Providers",
              children: (
                <Table
                  rowKey="provider_id"
                  columns={
                    providerColumns
                  }
                  dataSource={
                    providers
                  }
                  loading={
                    loadingProviders
                  }
                />
              ),
            },
            {
              key: "models",
              label: "Models",
              children: (
                <Table
                  rowKey="model_id"
                  columns={
                    modelColumns
                  }
                  dataSource={
                    models
                  }
                  loading={
                    loadingModels
                  }
                />
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title="Add AI Provider"
        open={
          createProviderVisible
        }
        onCancel={() =>
          setCreateProviderVisible(
            false
          )
        }
        onOk={handleCreateProvider}
      >
        <Form
          form={form}
          layout="vertical"
        >
          <Form.Item
            label="Provider Name"
            name="provider_name"
            rules={[
              {
                required: true,
              },
            ]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            label="Provider Type"
            name="provider_type"
            rules={[
              {
                required: true,
              },
            ]}
          >
            <Input
              placeholder="groq, openai, gemini..."
            />
          </Form.Item>

          <Form.Item
            label="Base URL"
            name="base_url"
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

export default AIProviderManagementModal;