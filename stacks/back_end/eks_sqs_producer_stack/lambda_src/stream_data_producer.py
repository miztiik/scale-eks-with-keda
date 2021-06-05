import json
import logging
import datetime
import time
import os
import random
import uuid
import boto3


class GlobalArgs:
    OWNER = "Mystique"
    VERSION = "2021-05-14"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    RELIABLE_QUEUE_NAME = os.getenv("RELIABLE_QUEUE_NAME")
    AWS_REGION = os.getenv("AWS_REGION")
    S3_BKT_NAME = os.getenv("STORE_EVENTS_BKT")
    S3_PREFIX = "sales_events"
    EVNT_WEIGHTS = {"success": 80, "fail": 20}
    WAIT_SECS_BETWEEN_MSGS = int(os.getenv("WAIT_SECS_BETWEEN_MSGS", 2))
    TOT_MSGS_TO_PRODUCE = int(os.getenv("TOT_MSGS_TO_PRODUCE", 10000))


def set_logging(lv=GlobalArgs.LOG_LEVEL):
    logging.basicConfig(level=lv)
    logger = logging.getLogger()
    logger.setLevel(lv)
    return logger


logger = set_logging()


def _rand_coin_flip():
    r = False
    if os.getenv("TRIGGER_RANDOM_FAILURES", True):
        if random.randint(1, 100) > 90:
            r = True
    return r


def _gen_uuid():
    return str(uuid.uuid4())


def get_q_url(sqs_client):
    q = sqs_client.get_queue_url(
        QueueName=GlobalArgs.RELIABLE_QUEUE_NAME).get("QueueUrl")
    logger.debug(f'{{"q_url":"{q}"}}')
    return q


def send_msg(sqs_client, q_url, msg_body, msg_attr=None):
    if not msg_attr:
        msg_attr = {}
    try:
        logger.debug(
            f'{{"msg_body":{msg_body}, "msg_attr": {json.dumps(msg_attr)}}}')
        resp = sqs_client.send_message(
            QueueUrl=q_url,
            MessageBody=msg_body,
            MessageAttributes=msg_attr
        )
    except Exception as e:
        logger.exception(f"ERROR:{str(e)}")
        raise e
    else:
        return resp


sqs_client = boto3.client("sqs", region_name=GlobalArgs.AWS_REGION)


def put_object(_pre, data):
    try:
        _r = _s3.put_object(
            Bucket=GlobalArgs.S3_BKT_NAME,
            Key=f"{GlobalArgs.S3_PREFIX}/event_type={_pre}/dt={datetime.datetime.now().strftime('%Y_%m_%d')}/{datetime.datetime.now().strftime('%s%f')}.json",
            Body=json.dumps(data).encode("UTF-8"),
        )
        logger.debug(f"resp: {json.dumps(_r)}")
    except Exception as e:
        logger.exception(f"ERROR:{str(e)}")


_s3 = boto3.client("s3")

end_time = datetime.datetime.now() + datetime.timedelta(seconds=10)


def lambda_handler(event, context):
    resp = {"status": False}
    logger.debug(f"Event: {json.dumps(event)}")
    _categories = ["Books", "Games", "Mobiles", "Groceries", "Shoes", "Stationaries", "Laptops",
                   "Tablets", "Notebooks", "Camera", "Printers", "Monitors", "Speakers", "Projectors", "Cables", "Furniture"]
    _evnt_types = ["sale_event", "inventory_event"]
    _variants = ["black", "red"]

    try:
        q_url = get_q_url(sqs_client)
        t_msgs = 0
        p_cnt = 0
        s_evnts = 0
        inventory_evnts = 0
        t_sales = 0
        while True:
            _s = round(random.random() * 100, 2)
            _evnt_type = random.choice(_evnt_types)
            _u = _gen_uuid()
            p_s = bool(random.getrandbits(1))
            evnt_body = {
                "request_id": _u,
                "store_id": random.randint(1, 10),
                "cust_id": random.randint(100, 999),
                "category": random.choice(_categories),
                "sku": random.randint(18981, 189281),
                "price": _s,
                "qty": random.randint(1, 38),
                "discount": round(random.random() * 20, 1),
                "gift_wrap": bool(random.getrandbits(1)),
                "variant": random.choice(_variants),
                "priority_shipping": p_s,
                "ts": datetime.datetime.now().isoformat(),
                "contact_me": "github.com/miztiik"
            }
            _attr = {
                "event_type": {
                    "DataType": "String",
                    "StringValue": _evnt_type
                },
                "priority_shipping": {
                    "DataType": "String",
                    "StringValue": f"{p_s}"
                }
            }

            # Make order type return
            if bool(random.getrandbits(1)):
                evnt_body["is_return"] = True

            if _rand_coin_flip():
                evnt_body.pop("store_id", None)
                evnt_body["bad_msg"] = True
                p_cnt += 1

            if _evnt_type == "sale_event":
                s_evnts += 1
            elif _evnt_type == "inventory_event":
                inventory_evnts += 1

            send_msg(
                sqs_client,
                q_url,
                json.dumps(evnt_body),
                _attr
            )
            t_msgs += 1
            t_sales += _s
            time.sleep(GlobalArgs.WAIT_SECS_BETWEEN_MSGS)
            # if context.get_remaining_time_in_millis() < 1000:
            # if datetime.datetime.now() >= end_time:
            if t_msgs >= GlobalArgs.TOT_MSGS_TO_PRODUCE:
                break

        resp["tot_msgs"] = t_msgs
        resp["bad_msgs"] = p_cnt
        resp["sale_evnts"] = s_evnts
        resp["inventory_evnts"] = inventory_evnts
        resp["tot_sales"] = t_sales
        resp["status"] = True
        logger.info(f'{{"resp":{json.dumps(resp)}}}')

    except Exception as e:
        logger.error(f"ERROR:{str(e)}")
        resp["err_msg"] = str(e)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": resp
        })
    }


lambda_handler({}, {})
