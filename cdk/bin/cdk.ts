#!/usr/bin/env node
import * as cdk from "aws-cdk-lib/core";
import { CdkStack } from "../lib/cdk-stack";

const app = new cdk.App();

const account = process.env.CDK_DEFAULT_ACCOUNT;

// Deploy to multiple regions
const regions = ["ap-northeast-1", "us-east-1", "eu-west-1"];

for (const region of regions) {
  new CdkStack(app, `IoTStack-${region}`, {
    env: { account, region },
  });
}
