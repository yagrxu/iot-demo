import { IoTClient, CreateThingCommand, DescribeThingCommand } from "@aws-sdk/client-iot";
import { IoTDataPlaneClient, PublishCommand } from "@aws-sdk/client-iot-data-plane";

const iot = new IoTClient({});
const iotData = new IoTDataPlaneClient({});

export const handler = async (event) => {
  const { gatewayName, thingName } = event;
  const replyTopic = `gateway/${gatewayName}/edge/register/reply`;

  console.log(`Edge registration request: ${thingName} from gateway ${gatewayName}`);

  try {
    // Check if thing already exists
    let exists = false;
    try {
      await iot.send(new DescribeThingCommand({ thingName }));
      exists = true;
      console.log(`Thing ${thingName} already exists.`);
    } catch (e) {
      if (e.name !== "ResourceNotFoundException") throw e;
    }

    // Create thing if not exists
    if (!exists) {
      await iot.send(new CreateThingCommand({
        thingName,
        attributePayload: {
          attributes: {
            gatewayName,
            deviceType: "edge",
          },
        },
      }));
      console.log(`Thing ${thingName} created.`);
    }

    // Reply to gateway via MQTT
    await iotData.send(new PublishCommand({
      topic: replyTopic,
      qos: 1,
      payload: JSON.stringify({
        thingName,
        status: "ok",
        created: !exists,
      }),
    }));

    return { status: "ok", thingName, created: !exists };
  } catch (err) {
    console.error(`Failed to register ${thingName}:`, err);

    // Notify gateway of failure
    await iotData.send(new PublishCommand({
      topic: replyTopic,
      qos: 1,
      payload: JSON.stringify({
        thingName,
        status: "error",
        error: err.message,
      }),
    }));

    throw err;
  }
};
