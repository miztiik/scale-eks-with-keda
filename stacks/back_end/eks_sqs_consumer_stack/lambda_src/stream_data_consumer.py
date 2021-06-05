# -*- coding: utf-8 -*-

import json
import logging
import os
import datetime
import time
import boto3


class GlobalArgs:
    OWNER = "Mystique"
    VERSION = "2021-05-14"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    AWS_REGION = os.getenv("AWS_REGION")
    RELIABLE_QUEUE_NAME = os.getenv("RELIABLE_QUEUE_NAME")
    MAX_MSGS_PER_BATCH = int(os.getenv("MAX_MSGS_PER_BATCH", 5))
    MSG_POLL_BACKOFF = int(os.getenv("MSG_POLL_BACKOFF", 2))
    MSG_PROCESS_DELAY = int(os.getenv("MSG_PROCESS_DELAY", 10))
    TOT_MSGS_TO_PROCESS = int(os.getenv("TOT_MSGS_TO_PROCESS", 10))
    S3_BKT_NAME = os.getenv("STORE_EVENTS_BKT")
    S3_PREFIX = "store_events"


def set_logging(lv=GlobalArgs.LOG_LEVEL):
    """ Helper to enable logging """
    logging.basicConfig(level=lv)
    logger = logging.getLogger()
    logger.setLevel(lv)
    return logger


logger = set_logging()
sqs_client = boto3.client("sqs", region_name=GlobalArgs.AWS_REGION)
_s3 = boto3.client("s3")


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


def get_q_url(sqs_client):
    q = sqs_client.get_queue_url(
        QueueName=GlobalArgs.RELIABLE_QUEUE_NAME).get("QueueUrl")
    logger.debug(f'{{"q_url":"{q}"}}')
    return q


def sqs_polling():
    no_msgs = False
    no_msg_cnt = 0
    back_off_secs = GlobalArgs.MSG_POLL_BACKOFF
    # poll sqs for 10000 Msgs
    t_msgs = 0
    while True:
        q_url = get_q_url(sqs_client)
        msg_batch = get_msgs(
            q_url, GlobalArgs.MAX_MSGS_PER_BATCH, GlobalArgs.MSG_POLL_BACKOFF)

        if len(msg_batch) == 0:
            no_msgs = True
        else:
            no_msgs = False

        # polling delay so aws does not throttle us
        time.sleep(GlobalArgs.MSG_PROCESS_DELAY)
        # sleep longer if there are no messages on the queue the last time it was polled
        if no_msgs:
            no_msg_cnt += 1
            back_off_secs = 2 * back_off_secs
            # HARD RESET, IF WE ARE WAITING FOR MESSAGES FOR LAST 10 MINUTES
            if back_off_secs > 512:
                back_off_secs = 2
            logger.info(f'{{"sleeping_for":"{back_off_secs}"}}')
            time.sleep(back_off_secs)

        # Process & Delete Messages
        m_stats = process_msgs(msg_batch)
        logger.info(f'{{"m_stats":"{json.dumps(m_stats)}"}}')
        t_msgs += m_stats["msg_batch"]

        # Break if we have processed X Msgs
        if t_msgs >= GlobalArgs.TOT_MSGS_TO_PROCESS:
            logger.info(f'{{"t_msgs":"{t_msgs}", "status":True }}')
            break


def get_msgs(q_url, max_msgs, wait_time):
    try:
        msg_batch = sqs_client.receive_message(
            QueueUrl=q_url,
            MaxNumberOfMessages=max_msgs,
            WaitTimeSeconds=wait_time,
            MessageAttributeNames=["All"]
        )
        logger.debug(f'{{"msg_batch":"{json.dumps(msg_batch)}"}}')
    except Exception as e:
        logger.exception(f"ERROR:{str(e)}")
        raise e
    else:
        return msg_batch


def process_msgs(msg_batch):
    try:
        m_process_stats = {
            "msg_batch": len(msg_batch["Messages"]),
            "s_msgs": 0,
            "f_msgs": 0
        }
        m_del_entries = []
        err = f'{{"missing_store_id":{True}}}'
        for m in msg_batch["Messages"]:
            m_del_entries.append(
                {"Id": m["MessageId"], "ReceiptHandle": m['ReceiptHandle']})
            d = json.loads(m["Body"])
            e_type = m["MessageAttributes"]["event_type"]["StringValue"]
            put_object(e_type, d)
            m_process_stats["s_msgs"] += 1
        # Trigger Message Batch Delete
        q_url = get_q_url(sqs_client)
        del_msgs(q_url, m_del_entries)
        logger.debug(f'{{"m_process_stats":"{json.dumps(m_process_stats)}"}}')

    except Exception as e:
        logger.exception(f"ERROR:{str(e)}")
        m_process_stats["f_msgs"] += 1
    else:
        return m_process_stats


def del_msgs(q_url, m_to_del):
    try:
        sqs_client.delete_message_batch(QueueUrl=q_url, Entries=m_to_del)
    except Exception as e:
        logger.exception(f"ERROR:{str(e)}")
        raise e


def lambda_handler(event, context):
    resp = {"status": False}
    logger.info(f"Event: {json.dumps(event)}")
    if event["Records"]:
        resp["tot_msgs"] = len(event["Records"])
        logger.info(f'{{"tot_msgs":{resp["tot_msgs"]}}}')
        m_process_stat = process_msgs(event["Records"])
        resp["s_msgs"] = m_process_stat.get("s_msgs")
        resp["status"] = True
        logger.info(f'{{"resp":{json.dumps(resp)}}}')

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": resp
        })
    }


sqs_polling()
