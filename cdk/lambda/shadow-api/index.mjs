import { IoTDataPlaneClient, GetThingShadowCommand, UpdateThingShadowCommand } from "@aws-sdk/client-iot-data-plane";
import { IoTClient, ListThingsCommand } from "@aws-sdk/client-iot";
import { DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";

const iotData = new IoTDataPlaneClient({});
const iot = new IoTClient({});
const dynamo = new DynamoDBClient({});
const TABLE_NAME = process.env.SHADOW_TABLE_NAME;

const headers = {
  "Content-Type": "application/json",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export const handler = async (event) => {
  const method = event.httpMethod;
  const path = event.path;

  try {
    // OPTIONS preflight
    if (method === "OPTIONS") {
      return { statusCode: 200, headers, body: "" };
    }

    // GET /things - list all things
    if (method === "GET" && path === "/things") {
      return await listThings();
    }

    // GET /things/{thingName}/shadow - get current shadow
    const shadowMatch = path.match(/^\/things\/([^/]+)\/shadow$/);
    if (method === "GET" && shadowMatch) {
      return await getShadow(shadowMatch[1]);
    }

    // POST /things/{thingName}/shadow - update desired state
    if (method === "POST" && shadowMatch) {
      const body = JSON.parse(event.body);
      return await updateShadow(shadowMatch[1], body);
    }

    // GET /things/{thingName}/history?limit=N - shadow history from DynamoDB
    const historyMatch = path.match(/^\/things\/([^/]+)\/history$/);
    if (method === "GET" && historyMatch) {
      const limit = parseInt(event.queryStringParameters?.limit || "20");
      return await getHistory(historyMatch[1], limit);
    }

    return { statusCode: 404, headers, body: JSON.stringify({ error: "Not found" }) };
  } catch (err) {
    console.error(err);
    return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
  }
};

async function listThings() {
  const res = await iot.send(new ListThingsCommand({ maxResults: 50 }));
  const things = (res.things || []).map((t) => ({
    thingName: t.thingName,
    thingArn: t.thingArn,
    attributes: t.attributes,
  }));
  return { statusCode: 200, headers, body: JSON.stringify(things) };
}

async function getShadow(thingName) {
  const res = await iotData.send(new GetThingShadowCommand({ thingName }));
  const payload = JSON.parse(new TextDecoder().decode(res.payload));
  return { statusCode: 200, headers, body: JSON.stringify(payload) };
}

async function updateShadow(thingName, body) {
  // body should be { desired: { key: value, ... } }
  const shadowPayload = JSON.stringify({ state: { desired: body.desired } });
  await iotData.send(
    new UpdateThingShadowCommand({
      thingName,
      payload: new TextEncoder().encode(shadowPayload),
    })
  );
  return { statusCode: 200, headers, body: JSON.stringify({ success: true }) };
}

async function getHistory(thingName, limit) {
  const res = await dynamo.send(
    new QueryCommand({
      TableName: TABLE_NAME,
      KeyConditionExpression: "thingName = :tn",
      ExpressionAttributeValues: { ":tn": { S: thingName } },
      ScanIndexForward: false,
      Limit: limit,
    })
  );
  const items = (res.Items || []).map((item) => ({
    thingName: item.thingName?.S,
    timestamp: Number(item.timestamp?.N),
    reported: item.reported?.M ? unmarshall(item.reported) : null,
    desired: item.desired?.M ? unmarshall(item.desired) : null,
  }));
  return { statusCode: 200, headers, body: JSON.stringify(items) };
}

// Simple DynamoDB unmarshall for nested maps
function unmarshall(attr) {
  if (!attr) return null;
  if (attr.S !== undefined) return attr.S;
  if (attr.N !== undefined) return Number(attr.N);
  if (attr.BOOL !== undefined) return attr.BOOL;
  if (attr.NULL) return null;
  if (attr.M) {
    const obj = {};
    for (const [k, v] of Object.entries(attr.M)) obj[k] = unmarshall(v);
    return obj;
  }
  if (attr.L) return attr.L.map(unmarshall);
  return null;
}
