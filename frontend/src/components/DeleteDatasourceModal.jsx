import React from 'react';
import {
  Modal,
  Card,
  Descriptions,
  List,
  Badge,
  Alert,
  Input,
  Button,
  Typography,
  Space,
} from 'antd';
import { CheckOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

const { Text, Title } = Typography;

const DeleteDatasourceModal = ({
  open,
  loading,
  deleteSummary,
  confirmText,
  setConfirmText,
  onDelete,
  onCancel,
  summaryError,
}) => {
  if (summaryError) {
    return (
      <Modal
        title="Delete Datasource"
        open={open}
        onCancel={onCancel}
        footer={[
          <Button key="back" onClick={onCancel}>
            Close
          </Button>,
        ]}
        width={700}
      >
        <Alert
          message="Failed to Load Summary"
          description={summaryError}
          type="error"
          showIcon
          style={{ margin: '2rem 0' }}
        />
      </Modal>
    );
  }

  // Graceful fallback if data isn't loaded yet
  if (!deleteSummary || !deleteSummary.connection || !deleteSummary.summary) {
    return (
      <Modal
        title="Delete Datasource"
        open={open}
        onCancel={onCancel}
        footer={null}
        width={700}
      >
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          Loading summary data...
        </div>
      </Modal>
    );
  }

  const { connection, summary } = deleteSummary;

  // Configuration for items that will be deleted
  const deletionImpactItems = [
    { label: 'Schema Tables', count: summary.schema_tables },
    { label: 'Schema Columns', count: summary.schema_columns },
    { label: 'Relationships', count: summary.schema_relationships },
    { label: 'Column Display Config', count: summary.column_display },
    { label: 'Schema Drift Events', count: summary.schema_drift_events },
    { label: 'Semantic Dimensions', count: summary.semantic_dimensions },
    { label: 'Semantic Metrics', count: summary.semantic_metrics },
    { label: 'Semantic Relationships', count: summary.semantic_relationships },
  ];

  return (
    <Modal
      title={
        <Text strong style={{ fontSize: '16px' }}>
          Delete Datasource
        </Text>
      }
      open={open}
      onCancel={onCancel}
      width={700}
      centered
      keyboard={true}
      maskClosable={false}
      footer={[
        <Button key="back" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>,
        <Button
          key="submit"
          type="primary"
          danger
          loading={loading}
          onClick={onDelete}
          disabled={confirmText !== connection.connection_name}
        >
          Delete Datasource
        </Button>,
      ]}
    >
      <Space direction="vertical" size="large" style={{ width: '100%', marginTop: '16px' }}>
        
        {/* Section 1: Datasource Information */}
        <Card 
          size="small" 
          title="Datasource Information" 
          style={{ borderRadius: '8px' }}
        >
          <Descriptions column={2} size="small">
            <Descriptions.Item label="Name">
              <Text strong>{connection.connection_name}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Database Type">
              {connection.database_type}
            </Descriptions.Item>
            <Descriptions.Item label="Database">
              {connection.database_name || 'N/A'}
            </Descriptions.Item>
            <Descriptions.Item label="Host">
              {connection.host}
            </Descriptions.Item>
            <Descriptions.Item label="Status">
              <Badge 
                status={connection.connection_status === 'ACTIVE' ? 'success' : 'default'} 
                text={connection.connection_status} 
              />
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* Section 2: Deletion Impact */}
        <Card 
          size="small" 
          title="Items that will be permanently removed" 
          style={{ borderRadius: '8px', borderColor: '#ffa39e', backgroundColor: '#fff1f0' }}
          headStyle={{ color: '#cf1322' }}
        >
          <List
            size="small"
            dataSource={deletionImpactItems}
            split={false}
            renderItem={(item) => (
              <List.Item style={{ padding: '4px 0' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <CheckOutlined style={{ color: '#ff4d4f' }} />
                    <Text>{item.label}</Text>
                  </Space>
                  <Badge
                    count={item.count}
                    showZero
                    style={{ backgroundColor: '#ffccc7', color: '#cf1322' }}
                  />
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Section 3: Audit Preservation */}
        <Card 
          size="small" 
          title="Items that will be preserved" 
          style={{ borderRadius: '8px', borderColor: '#b7eb8f', backgroundColor: '#f6ffed' }}
          headStyle={{ color: '#389e0d' }}
        >
          <List
            size="small"
            dataSource={[{ label: 'Lifecycle Audit Events', count: summary.lifecycle_events }]}
            split={false}
            renderItem={(item) => (
              <List.Item style={{ padding: '4px 0' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <SafetyCertificateOutlined style={{ color: '#52c41a' }} />
                    <Text strong style={{ color: '#389e0d' }}>{item.label}</Text>
                  </Space>
                  <Badge
                    count={item.count}
                    showZero
                    style={{ backgroundColor: '#d9f7be', color: '#237804' }}
                  />
                </Space>
              </List.Item>
            )}
          />
          <div style={{ marginTop: '8px' }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              Lifecycle history is retained permanently for auditing and compliance.
            </Text>
          </div>
        </Card>

        {/* Section 4: Danger Warning */}
        <Alert
          type="warning"
          showIcon
          message={
            <Text strong>
              Deleting this datasource permanently removes all synchronized metadata and semantic configurations.
            </Text>
          }
          description="This action cannot be undone."
          style={{ borderRadius: '8px' }}
        />

        {/* Section 5: Confirmation */}
        <div style={{ padding: '8px 0' }}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Text>To confirm deletion, type the datasource name exactly: <b>{connection.connection_name}</b></Text>
            <Input
              placeholder="Enter datasource name"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              onPressEnter={(e) => {
                // Prevent Enter key from deleting if text doesn't match
                if (confirmText === connection.connection_name) {
                  onDelete();
                }
              }}
              autoComplete="off"
              size="large"
            />
          </Space>
        </div>

      </Space>
    </Modal>
  );
};

export default DeleteDatasourceModal;
