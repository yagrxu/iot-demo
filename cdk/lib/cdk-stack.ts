import * as cdk from "aws-cdk-lib";
import * as path from "path";
import { Construct } from "constructs";
import * as iot from "aws-cdk-lib/aws-iot";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigw from "aws-cdk-lib/aws-apigateway";

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ---- DynamoDB Table for Shadow data ----
    const shadowTable = new dynamodb.Table(this, "DeviceShadowTable", {
      tableName: "DeviceShadows",
      partitionKey: { name: "thingName", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ---- IAM Role for IoT Rule -> DynamoDB ----
    const iotRuleRole = new iam.Role(this, "IoTRuleDynamoDBRole", {
      assumedBy: new iam.ServicePrincipal("iot.amazonaws.com"),
    });
    shadowTable.grantWriteData(iotRuleRole);

    // ---- IoT Rule: Shadow -> DynamoDB ----
    new iot.CfnTopicRule(this, "ShadowToDynamoDBRule", {
      ruleName: "ShadowToDynamoDB",
      topicRulePayload: {
        sql: `SELECT topic(3) AS thingName, timestamp() AS timestamp, state.reported AS reported, state.desired AS desired FROM '$aws/things/+/shadow/update/documents'`,
        awsIotSqlVersion: "2016-03-23",
        actions: [
          {
            dynamoDBv2: {
              putItem: { tableName: shadowTable.tableName },
              roleArn: iotRuleRole.roleArn,
            },
          },
        ],
      },
    });

    // ---- IoT Policy for provisioned devices ----
    const devicePolicy = new iot.CfnPolicy(this, "DevicePolicy", {
      policyName: "DevicePolicy",
      policyDocument: {
        Version: "2012-10-17",
        Statement: [
          {
            Effect: "Allow",
            Action: ["iot:Connect"],
            Resource: [
              `arn:aws:iot:${this.region}:${this.account}:client/\${iot:Connection.Thing.ThingName}`,
            ],
          },
          {
            Effect: "Allow",
            Action: ["iot:Publish", "iot:Receive"],
            Resource: [
              `arn:aws:iot:${this.region}:${this.account}:topic/$aws/things/\${iot:Connection.Thing.ThingName}/shadow/*`,
            ],
          },
          {
            Effect: "Allow",
            Action: ["iot:Subscribe"],
            Resource: [
              `arn:aws:iot:${this.region}:${this.account}:topicfilter/$aws/things/\${iot:Connection.Thing.ThingName}/shadow/*`,
            ],
          },
        ],
      },
    });

    // ---- Fleet Provisioning Role ----
    const provisioningRole = new iam.Role(this, "FleetProvisioningRole", {
      assumedBy: new iam.ServicePrincipal("iot.amazonaws.com"),
      inlinePolicies: {
        ProvisioningPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                "iot:AddThingToThingGroup",
                "iot:AttachPrincipalPolicy",
                "iot:AttachThingPrincipal",
                "iot:CreateThing",
                "iot:CreatePolicy",
                "iot:DescribeCertificate",
                "iot:DescribeThing",
                "iot:DescribeThingGroup",
                "iot:DescribeThingType",
                "iot:GetPolicy",
                "iot:ListPolicyPrincipals",
                "iot:ListPrincipalPolicies",
                "iot:ListPrincipalThings",
                "iot:ListTargetsForPolicy",
                "iot:ListThingGroupsForThing",
                "iot:ListThingPrincipals",
                "iot:RegisterCertificate",
                "iot:RegisterThing",
                "iot:UpdateCertificate",
                "iot:UpdateThing",
              ],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // ---- Fleet Provisioning Template ----
    new iot.CfnProvisioningTemplate(this, "FleetProvisioningTemplate", {
      templateName: "FleetProvisioningTemplate",
      enabled: true,
      provisioningRoleArn: provisioningRole.roleArn,
      templateBody: JSON.stringify({
        Parameters: {
          ThingName: { Type: "String" },
          "AWS::IoT::Certificate::Id": { Type: "String" },
          SerialNumber: { Type: "String" },
        },
        Resources: {
          thing: {
            Type: "AWS::IoT::Thing",
            Properties: {
              ThingName: { Ref: "ThingName" },
              AttributePayload: {
                serialNumber: { Ref: "SerialNumber" },
              },
            },
          },
          certificate: {
            Type: "AWS::IoT::Certificate",
            Properties: {
              CertificateId: { Ref: "AWS::IoT::Certificate::Id" },
              Status: "Active",
            },
          },
          policy: {
            Type: "AWS::IoT::Policy",
            Properties: {
              PolicyName: devicePolicy.policyName!,
            },
          },
        },
      }),
    });

    // ---- Claim Policy (for temporary claim cert) ----
    new iot.CfnPolicy(this, "ClaimPolicy", {
      policyName: "ClaimPolicy",
      policyDocument: {
        Version: "2012-10-17",
        Statement: [
          {
            Effect: "Allow",
            Action: ["iot:Connect"],
            Resource: ["*"],
          },
          {
            Effect: "Allow",
            Action: ["iot:Publish", "iot:Receive"],
            Resource: [
              `arn:aws:iot:${this.region}:${this.account}:topic/$aws/certificates/create/*`,
              `arn:aws:iot:${this.region}:${this.account}:topic/$aws/provisioning-templates/FleetProvisioningTemplate/provision/*`,
            ],
          },
          {
            Effect: "Allow",
            Action: ["iot:Subscribe"],
            Resource: [
              `arn:aws:iot:${this.region}:${this.account}:topicfilter/$aws/certificates/create/*`,
              `arn:aws:iot:${this.region}:${this.account}:topicfilter/$aws/provisioning-templates/FleetProvisioningTemplate/provision/*`,
            ],
          },
        ],
      },
    });

    // ---- Outputs ----
    new cdk.CfnOutput(this, "ShadowTableName", {
      value: shadowTable.tableName,
    });

    // ---- Lambda: Shadow API ----
    const shadowApiHandler = new lambda.Function(this, "ShadowApiHandler", {
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: "index.handler",
      code: lambda.Code.fromAsset(path.join(__dirname, "../lambda/shadow-api")),
      environment: {
        SHADOW_TABLE_NAME: shadowTable.tableName,
      },
      timeout: cdk.Duration.seconds(10),
    });

    shadowTable.grantReadData(shadowApiHandler);
    shadowApiHandler.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "iot:GetThingShadow",
          "iot:UpdateThingShadow",
          "iot:ListThings",
        ],
        resources: ["*"],
      })
    );

    // ---- API Gateway ----
    const api = new apigw.RestApi(this, "ShadowApi", {
      restApiName: "IoT Shadow API",
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,
      },
    });

    const lambdaIntegration = new apigw.LambdaIntegration(shadowApiHandler);

    // GET /things
    const things = api.root.addResource("things");
    things.addMethod("GET", lambdaIntegration);

    // GET/POST /things/{thingName}/shadow
    const thing = things.addResource("{thingName}");
    const shadow = thing.addResource("shadow");
    shadow.addMethod("GET", lambdaIntegration);
    shadow.addMethod("POST", lambdaIntegration);

    // GET /things/{thingName}/history
    const history = thing.addResource("history");
    history.addMethod("GET", lambdaIntegration);

    new cdk.CfnOutput(this, "ApiUrl", {
      value: api.url,
    });
  }
}
