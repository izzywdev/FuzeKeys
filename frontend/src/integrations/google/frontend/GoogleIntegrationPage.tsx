import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Tabs, 
  Typography, 
  Space, 
  Alert, 
  Button, 
  Table, 
  Tag, 
  Modal,
  notification
} from 'antd';
import { 
  GoogleOutlined, 
  ReloadOutlined, 
  ExperimentOutlined,
  HistoryOutlined
} from '@ant-design/icons';

import GoogleSignupForm from './components/GoogleSignupForm';
import googleApiService, { 
  GoogleSignupData, 
  GoogleSignupConfig, 
  GoogleSignupResult, 
  GoogleAccount,
  Identity 
} from './services/googleApi';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

interface TestResult {
  success: boolean;
  message: string;
  signup_data?: any;
}

const GoogleIntegrationPage: React.FC = () => {
  // State management
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [accounts, setAccounts] = useState<GoogleAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [selectedIdentityForAccounts, setSelectedIdentityForAccounts] = useState<number | null>(null);
  const [lastSignupResult, setLastSignupResult] = useState<GoogleSignupResult | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testModalVisible, setTestModalVisible] = useState(false);

  // Load initial data
  useEffect(() => {
    loadIdentities();
  }, []);

  const loadIdentities = async () => {
    try {
      const identitiesData = await googleApiService.getIdentities();
      setIdentities(identitiesData);
    } catch (error: any) {
      notification.error({
        message: 'Failed to load identities',
        description: error.message,
      });
    }
  };

  const loadAccounts = async (identityId: number) => {
    try {
      setLoading(true);
      const response = await googleApiService.getGoogleAccounts(identityId);
      setAccounts(response.accounts);
      setSelectedIdentityForAccounts(identityId);
    } catch (error: any) {
      notification.error({
        message: 'Failed to load accounts',
        description: error.message,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async (
    identityId?: number,
    manualData?: GoogleSignupData,
    config?: GoogleSignupConfig
  ) => {
    try {
      setLoading(true);
      let result: GoogleSignupResult;

      if (identityId) {
        result = await googleApiService.signupWithIdentity(identityId, config);
      } else if (manualData) {
        result = await googleApiService.signupWithManualData(manualData, config);
      } else {
        throw new Error('Either identity ID or manual data must be provided');
      }

      setLastSignupResult(result);

      if (result.success) {
        notification.success({
          message: 'Google Account Created!',
          description: `Account ${result.account_email} was created successfully.`,
          duration: 5,
        });

        // Refresh accounts if we have a selected identity
        if (selectedIdentityForAccounts) {
          await loadAccounts(selectedIdentityForAccounts);
        }
      } else {
        notification.warning({
          message: 'Signup Incomplete',
          description: result.message,
          duration: 8,
        });
      }
    } catch (error: any) {
      notification.error({
        message: 'Signup Failed',
        description: error.message,
        duration: 10,
      });
      
      setLastSignupResult({
        success: false,
        message: error.message,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTestIdentityConversion = async (identityId: number) => {
    try {
      setTestLoading(true);
      const result = await googleApiService.testIdentityConversion(identityId);
      setTestResult(result);
      setTestModalVisible(true);
    } catch (error: any) {
      notification.error({
        message: 'Test Failed',
        description: error.message,
      });
    } finally {
      setTestLoading(false);
    }
  };

  const accountsColumns = [
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      render: (email: string) => (
        <Space>
          <GoogleOutlined style={{ color: '#1890ff' }} />
          <Text strong>{email}</Text>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const color = status === 'active' ? 'green' : 
                     status === 'verification_required' ? 'orange' : 'red';
        return <Tag color={color}>{status.replace('_', ' ').toUpperCase()}</Tag>;
      },
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: GoogleAccount) => (
        <Space>
          <Button 
            size="small" 
            onClick={() => window.open(`https://accounts.google.com`, '_blank')}
          >
            Open Gmail
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ textAlign: 'center' }}>
          <GoogleOutlined style={{ fontSize: '64px', color: '#1890ff', marginBottom: '16px' }} />
          <Title level={1}>Google Integration</Title>
          <Text type="secondary">
            Automate Google account creation and management
          </Text>
        </div>

        <Tabs defaultActiveKey="signup" size="large">
          <TabPane tab="Create Account" key="signup" icon={<GoogleOutlined />}>
            <GoogleSignupForm
              onSignup={handleGoogleSignup}
              loading={loading}
              identities={identities}
            />

            {/* Last Result Display */}
            {lastSignupResult && (
              <Card style={{ marginTop: '24px' }} title="Last Signup Result">
                <Alert
                  type={lastSignupResult.success ? 'success' : 'error'}
                  message={lastSignupResult.success ? 'Success!' : 'Failed'}
                  description={
                    <div>
                      <p>{lastSignupResult.message}</p>
                      {lastSignupResult.account_email && (
                        <p><strong>Email:</strong> {lastSignupResult.account_email}</p>
                      )}
                      {lastSignupResult.verification_required && (
                        <p><strong>Verification Required:</strong> {lastSignupResult.verification_type}</p>
                      )}
                    </div>
                  }
                  showIcon
                />
              </Card>
            )}
          </TabPane>

          <TabPane tab="Account Management" key="accounts" icon={<HistoryOutlined />}>
            <Card title="Google Accounts">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <Text strong>Select Identity to view accounts:</Text>
                  <div style={{ marginTop: '8px' }}>
                    {identities.map(identity => (
                      <Button
                        key={identity.id}
                        type={selectedIdentityForAccounts === identity.id ? 'primary' : 'default'}
                        onClick={() => loadAccounts(identity.id)}
                        style={{ marginRight: '8px', marginBottom: '8px' }}
                        loading={loading}
                      >
                        {identity.name}
                      </Button>
                    ))}
                  </div>
                </div>

                {selectedIdentityForAccounts && (
                  <div>
                    <div style={{ marginBottom: '16px' }}>
                      <Button
                        icon={<ReloadOutlined />}
                        onClick={() => loadAccounts(selectedIdentityForAccounts)}
                        loading={loading}
                      >
                        Refresh
                      </Button>
                    </div>

                    <Table
                      dataSource={accounts}
                      columns={accountsColumns}
                      rowKey="id"
                      loading={loading}
                      pagination={false}
                      locale={{
                        emptyText: 'No Google accounts found for this identity'
                      }}
                    />
                  </div>
                )}
              </Space>
            </Card>
          </TabPane>

          <TabPane tab="Testing Tools" key="testing" icon={<ExperimentOutlined />}>
            <Card title="Identity Conversion Test">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Alert
                  type="info"
                  message="Test identity conversion without creating an account"
                  description="This will show you what data would be used for Google signup based on your identity information."
                  showIcon
                />

                <div>
                  <Text strong>Select Identity to test:</Text>
                  <div style={{ marginTop: '8px' }}>
                    {identities.map(identity => (
                      <Button
                        key={identity.id}
                        onClick={() => handleTestIdentityConversion(identity.id)}
                        loading={testLoading}
                        style={{ marginRight: '8px', marginBottom: '8px' }}
                        icon={<ExperimentOutlined />}
                      >
                        Test {identity.name}
                      </Button>
                    ))}
                  </div>
                </div>
              </Space>
            </Card>
          </TabPane>
        </Tabs>

        {/* Test Result Modal */}
        <Modal
          title="Identity Conversion Test Result"
          visible={testModalVisible}
          onCancel={() => setTestModalVisible(false)}
          footer={[
            <Button key="close" onClick={() => setTestModalVisible(false)}>
              Close
            </Button>
          ]}
          width={600}
        >
          {testResult && (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert
                type={testResult.success ? 'success' : 'error'}
                message={testResult.message}
                showIcon
              />
              
              {testResult.success && testResult.signup_data && (
                <Card size="small" title="Generated Signup Data">
                  <pre style={{ 
                    backgroundColor: '#f5f5f5', 
                    padding: '12px', 
                    borderRadius: '4px',
                    overflow: 'auto'
                  }}>
                    {JSON.stringify(testResult.signup_data, null, 2)}
                  </pre>
                </Card>
              )}
            </Space>
          )}
        </Modal>
      </Space>
    </div>
  );
};

export default GoogleIntegrationPage; 